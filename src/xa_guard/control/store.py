"""Async PostgreSQL assignment, effect, approval, and worker queue store."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import uuid
import weakref
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from xa_guard.control.crypto import EncryptedEnvelope, Keyring, canonical_json, sha256_json
from xa_guard.control.key_provider import KeyProvider, LocalKeyProvider
from xa_guard.control.models import EffectContractV2, Principal
from xa_guard.control.timing import add_duration, span


class StoreError(RuntimeError):
    code = "store_error"


class NotFoundError(StoreError):
    code = "not_found"


class ConflictError(StoreError):
    code = "conflict"


class AuthorizationError(StoreError):
    code = "forbidden"


class _ChainTailConflict(StoreError):
    pass


@dataclass
class _PreparedEffectMutation:
    effect_id: str
    insert_args: tuple[Any, ...]
    tenant_id: str
    actor: str
    trace_id: str
    future: asyncio.Future[str]


@dataclass
class _Gate6Mutation:
    tenant_id: str
    trace_id: str
    record: dict[str, Any]
    source_instance: str
    signer: Callable[[bytes], str] | None
    future: asyncio.Future[dict[str, Any]]


@dataclass
class _CompletedEffectMutation:
    effect_id: str
    tenant_id: str
    actor: str
    status: str
    tool_name: str
    reversibility: str
    encrypted: EncryptedEnvelope
    result_sha256: str
    downstream_reference: str
    future: asyncio.Future[None]


@dataclass
class _FinalEffectAuditMutation:
    effect: _CompletedEffectMutation
    gate6: _Gate6Mutation


@dataclass
class _PreparedEffectAuditMutation:
    effect: _PreparedEffectMutation
    gate6: _Gate6Mutation


class AsyncEffectStore:
    MIGRATION_LOCK_ID = 0x58414744

    def __init__(self, dsn: str, keyring: Keyring | KeyProvider | None = None) -> None:
        self.dsn = dsn
        if isinstance(keyring, Keyring):
            self.keyring: Keyring | None = keyring
            self.key_provider: KeyProvider | None = LocalKeyProvider(keyring)
        else:
            self.key_provider = keyring
            self.keyring = getattr(keyring, "keyring", None)
        self.pool: Any = None
        # PostgreSQL advisory locks remain the cross-replica source of truth.
        # This process-local layer prevents a burst for one tenant from taking
        # every asyncpg connection while those connections wait on the same
        # advisory lock. Weak values keep inactive tenant keys from becoming an
        # unbounded in-memory registry.
        self._chain_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()
        self._chain_tail_cache: dict[tuple[str, str], str] = {}
        self._effect_batches: dict[
            str, list[_PreparedEffectMutation | _CompletedEffectMutation]
        ] = {}
        self._effect_flush_tasks: dict[str, asyncio.Task[None]] = {}
        self._gate6_batches: dict[str, list[_Gate6Mutation]] = {}
        self._gate6_flush_tasks: set[asyncio.Task[None]] = set()
        self._gate6_workers: dict[str, asyncio.Task[None]] = {}
        self._staged_completions: dict[str, _CompletedEffectMutation] = {}
        self._staged_pre_audits: dict[str, _Gate6Mutation] = {}
        self._prepared_audit_batches: dict[
            str, list[_PreparedEffectAuditMutation]
        ] = {}
        self._final_batches: dict[str, list[_FinalEffectAuditMutation]] = {}
        self._effect_audit_tasks: dict[str, asyncio.Task[None]] = {}

    def _chain_lock(self, chain: str, tenant_id: str) -> asyncio.Lock:
        key = f"{chain}:{tenant_id}"
        lock = self._chain_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._chain_locks[key] = lock
        return lock

    @asynccontextmanager
    async def _chain_connection(self, chain: str, tenant_id: str):
        started = asyncio.get_running_loop().time()
        async with self._chain_lock(chain, tenant_id):
            add_duration(
                f"xa-chain-{chain}-wait",
                (asyncio.get_running_loop().time() - started) * 1000.0,
            )
            with span(f"xa-chain-{chain}-transaction"):
                async with self.pool.acquire() as conn, conn.transaction():
                    yield conn

    @asynccontextmanager
    async def _effect_gate6_connection(self, tenant_id: str):
        async with self._chain_lock('effect', tenant_id):
            async with self._chain_lock('gate6', tenant_id):
                async with self.pool.acquire() as conn, conn.transaction():
                    yield conn

    @staticmethod
    async def _execute_many(conn: Any, query: str, rows: list[tuple[Any, ...]]) -> None:
        executemany = getattr(conn, "executemany", None)
        if executemany is not None:
            await executemany(query, rows)
            return
        for row in rows:
            await conn.execute(query, *row)

    @staticmethod
    async def _lock_and_read_chain_tail(conn: Any, chain: str, tenant_id: str) -> str:
        if chain not in {"effect", "gate6"}:
            raise ValueError("unsupported chain")
        if getattr(conn, 'executemany', None) is not None:
            await conn.execute(
                '''
                INSERT INTO xa_chain_tails(chain,tenant_id,tail_hash)
                VALUES($1,$2,'') ON CONFLICT (chain,tenant_id) DO NOTHING
                ''',
                chain,
                tenant_id,
            )
            return (
                await conn.fetchval(
                    '''
                    SELECT tail_hash FROM xa_chain_tails
                    WHERE chain=$1 AND tenant_id=$2 FOR UPDATE
                    ''',
                    chain,
                    tenant_id,
                )
                or ''
            )
        table = "xa_effect_events" if chain == "effect" else "xa_gate6_events"
        await conn.execute(
            "SELECT pg_advisory_xact_lock(hashtext($1))", f"{chain}-chain:{tenant_id}"
        )
        return (
            await conn.fetchval(
                f"SELECT record_hash FROM {table} "
                "WHERE tenant_id=$1 ORDER BY seq DESC LIMIT 1",
                tenant_id,
            )
            or ""
        )

    async def _cached_tail_pair(self, conn: Any, tenant_id: str) -> tuple[str, str]:
        effect_key = ('effect', tenant_id)
        gate_key = ('gate6', tenant_id)
        if effect_key in self._chain_tail_cache and gate_key in self._chain_tail_cache:
            return self._chain_tail_cache[effect_key], self._chain_tail_cache[gate_key]
        await conn.execute(
            '''
            INSERT INTO xa_chain_tails(chain,tenant_id,tail_hash)
            VALUES('effect',$1,''),('gate6',$1,'')
            ON CONFLICT (chain,tenant_id) DO NOTHING
            ''',
            tenant_id,
        )
        rows = await conn.fetch(
            '''
            SELECT chain,tail_hash FROM xa_chain_tails
            WHERE tenant_id=$1 AND chain IN ('effect','gate6')
            ''',
            tenant_id,
        )
        tails = {str(row['chain']): str(row['tail_hash']) for row in rows}
        if set(tails) != {'effect', 'gate6'}:
            raise StoreError('chain tail rows are unavailable')
        self._chain_tail_cache[effect_key] = tails['effect']
        self._chain_tail_cache[gate_key] = tails['gate6']
        return tails['effect'], tails['gate6']

    async def _refresh_tail_pair(self, conn: Any, tenant_id: str) -> tuple[str, str]:
        self._chain_tail_cache.pop(('effect', tenant_id), None)
        self._chain_tail_cache.pop(('gate6', tenant_id), None)
        return await self._cached_tail_pair(conn, tenant_id)

    async def _write_chain_tail(
        self, conn: Any, chain: str, tenant_id: str, tail_hash: str
    ) -> None:
        if getattr(conn, 'executemany', None) is None:
            return
        await conn.execute(
            '''
            UPDATE xa_chain_tails SET tail_hash=$3,updated_at=now()
            WHERE chain=$1 AND tenant_id=$2
            ''',
            chain,
            tenant_id,
            tail_hash,
        )
        self._chain_tail_cache.pop((chain, tenant_id), None)

    @staticmethod
    async def _insert_effect_events(
        conn: Any, tenant_id: str, rows: list[tuple[Any, ...]]
    ) -> None:
        await conn.execute(
            """
            INSERT INTO xa_effect_events(
              tenant_id,effect_id,event_type,actor_sub,payload,prev_hash,record_hash
            )
            SELECT $1,input.effect_id,input.event_type,input.actor_sub,input.payload,
                   input.prev_hash,input.record_hash
              FROM unnest($2::text[],$3::text[],$4::text[],$5::jsonb[],$6::text[],$7::text[])
                   WITH ORDINALITY AS input(
                     effect_id,event_type,actor_sub,payload,prev_hash,record_hash,ordinality
                   )
             ORDER BY input.ordinality
            """,
            tenant_id,
            [row[1] for row in rows],
            [row[2] for row in rows],
            [row[3] for row in rows],
            [row[4] for row in rows],
            [row[5] for row in rows],
            [row[6] for row in rows],
        )

    @staticmethod
    async def _insert_prepared_effects(
        conn: Any, batch: list[_PreparedEffectMutation]
    ) -> None:
        query = """
            INSERT INTO xa_effects(
              effect_id,tenant_id,trace_id,principal_sub,principal_username,agent_id,data_domain,
              tool_name,args_sha256,contract_version,contract_hash,contract_snapshot,side_effect_level,
              reversibility,status,undo_expires_at,lease_owner,lease_until,heartbeat_at,
              authorization_snapshot)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12::jsonb,$13,$14,'prepared',
                   now()+make_interval(secs=>$15),$16,now()+make_interval(secs=>60),now(),$17::jsonb)
        """
        if getattr(conn, "executemany", None) is None:
            await AsyncEffectStore._execute_many(
                conn, query, [mutation.insert_args for mutation in batch]
            )
            return
        rows = [mutation.insert_args for mutation in batch]
        await conn.execute(
            """
            INSERT INTO xa_effects(
              effect_id,tenant_id,trace_id,principal_sub,principal_username,agent_id,data_domain,
              tool_name,args_sha256,contract_version,contract_hash,contract_snapshot,side_effect_level,
              reversibility,status,undo_expires_at,lease_owner,lease_until,heartbeat_at,
              authorization_snapshot)
            SELECT input.effect_id,input.tenant_id,input.trace_id,input.principal_sub,
                   input.principal_username,input.agent_id,input.data_domain,input.tool_name,
                   input.args_sha256,input.contract_version,input.contract_hash,input.contract_snapshot,
                   input.side_effect_level,input.reversibility,'prepared',
                   now()+make_interval(secs=>input.undo_window_seconds),input.lease_owner,
                   now()+make_interval(secs=>60),now(),input.authorization_snapshot
              FROM unnest(
                     $1::text[],$2::text[],$3::text[],$4::text[],$5::text[],$6::text[],$7::text[],
                     $8::text[],$9::text[],$10::text[],$11::text[],$12::jsonb[],$13::text[],
                     $14::text[],$15::integer[],$16::text[],$17::jsonb[]
                   ) AS input(
                     effect_id,tenant_id,trace_id,principal_sub,principal_username,agent_id,
                     data_domain,tool_name,args_sha256,contract_version,contract_hash,
                     contract_snapshot,side_effect_level,reversibility,undo_window_seconds,
                     lease_owner,authorization_snapshot
                   )
            """,
            *[[row[index] for row in rows] for index in range(17)],
        )

    @staticmethod
    async def _update_completed_effects(
        conn: Any, tenant_id: str, batch: list[_CompletedEffectMutation]
    ) -> None:
        fetch = getattr(conn, 'fetch', None)
        if fetch is not None:
            updated = await fetch(
                '''
                UPDATE xa_effects AS effect
                   SET status=input.status,completed_at=now(),updated_at=now(),
                       key_id=input.key_id,wrapped_dek=input.wrapped_dek,
                       recovery_nonce=input.recovery_nonce,
                       recovery_ciphertext=input.recovery_ciphertext,
                       result_sha256=input.result_sha256,
                       downstream_reference=input.downstream_reference,
                       lease_owner=NULL,lease_until=NULL,heartbeat_at=NULL
                  FROM unnest(
                    $1::text[],$2::text[],$3::text[],$4::bytea[],$5::bytea[],
                    $6::bytea[],$7::text[],$8::text[],$9::text[],$10::text[]
                  ) AS input(
                    effect_id,status,key_id,wrapped_dek,recovery_nonce,
                    recovery_ciphertext,result_sha256,downstream_reference,
                    tool_name,reversibility
                  )
                 WHERE effect.effect_id=input.effect_id
                   AND effect.tenant_id=$11
                   AND effect.tool_name=input.tool_name
                   AND effect.reversibility=input.reversibility
                   AND effect.status='prepared'
                RETURNING effect.effect_id
                ''',
                [item.effect_id for item in batch],
                [item.status for item in batch],
                [item.encrypted.key_id for item in batch],
                [item.encrypted.wrapped_dek for item in batch],
                [item.encrypted.nonce for item in batch],
                [item.encrypted.ciphertext for item in batch],
                [item.result_sha256 for item in batch],
                [item.downstream_reference for item in batch],
                [item.tool_name for item in batch],
                [item.reversibility for item in batch],
                tenant_id,
            )
            actual = {str(row['effect_id']) for row in updated}
            expected = {item.effect_id for item in batch}
            if actual != expected:
                raise ConflictError('effect is absent or no longer prepared')
            return
        for mutation in batch:
            changed = await conn.fetchval(
                """
                UPDATE xa_effects SET status=$1,completed_at=now(),updated_at=now(),key_id=$2,
                  wrapped_dek=$3,recovery_nonce=$4,recovery_ciphertext=$5,result_sha256=$6,
                  downstream_reference=$7,lease_owner=NULL,lease_until=NULL,heartbeat_at=NULL
                 WHERE effect_id=$8 AND tenant_id=$9 AND tool_name=$10 AND reversibility=$11
                   AND status='prepared' RETURNING 1
                """,
                mutation.status,
                mutation.encrypted.key_id,
                mutation.encrypted.wrapped_dek,
                mutation.encrypted.nonce,
                mutation.encrypted.ciphertext,
                mutation.result_sha256,
                mutation.downstream_reference,
                mutation.effect_id,
                tenant_id,
                mutation.tool_name,
                mutation.reversibility,
            )
            if changed is None:
                raise ConflictError("effect is absent or no longer prepared")

    async def _persist_effect_mutations(
        self,
        tenant_id: str,
        batch: list[_PreparedEffectMutation | _CompletedEffectMutation],
    ) -> None:
        async with self._chain_connection('effect', tenant_id) as conn:
            prepared = [
                item for item in batch if isinstance(item, _PreparedEffectMutation)
            ]
            completed = [
                item for item in batch if isinstance(item, _CompletedEffectMutation)
            ]
            if prepared:
                await self._insert_prepared_effects(conn, prepared)
            if completed:
                await self._update_completed_effects(conn, tenant_id, completed)
            previous = await self._lock_and_read_chain_tail(conn, 'effect', tenant_id)
            event_rows: list[tuple[Any, ...]] = []
            for mutation in batch:
                if isinstance(mutation, _PreparedEffectMutation):
                    event_type = 'effect_prepared'
                    payload = {'trace_id': mutation.trace_id}
                else:
                    event_type = (
                        'effect_available'
                        if mutation.status == 'available'
                        else mutation.status
                    )
                    payload = {'result_sha256': mutation.result_sha256}
                value = {
                    'tenant_id': tenant_id,
                    'effect_id': mutation.effect_id,
                    'event_type': event_type,
                    'actor_sub': mutation.actor,
                    'payload': payload,
                    'prev_hash': previous,
                }
                record_hash = sha256_json(value)
                event_rows.append(
                    (
                        tenant_id,
                        mutation.effect_id,
                        event_type,
                        mutation.actor,
                        payload,
                        previous,
                        record_hash,
                    )
                )
                previous = record_hash
            await self._insert_effect_events(conn, tenant_id, event_rows)
            await self._write_chain_tail(
                conn, 'effect', tenant_id, previous
            )

    async def _enqueue_effect_mutation(
        self, mutation: _PreparedEffectMutation | _CompletedEffectMutation
    ) -> str | None:
        queue = self._effect_batches.setdefault(mutation.tenant_id, [])
        queue.append(mutation)
        task = self._effect_flush_tasks.get(mutation.tenant_id)
        if task is None or task.done():
            self._effect_flush_tasks[mutation.tenant_id] = asyncio.create_task(
                self._flush_effect_mutations(mutation.tenant_id)
            )
        return await asyncio.shield(mutation.future)

    async def _flush_effect_mutations(self, tenant_id: str) -> None:
        try:
            while True:
                await asyncio.sleep(0.001)
                batch = self._effect_batches.pop(tenant_id, [])
                if not batch:
                    return
                try:
                    await self._persist_effect_mutations(tenant_id, batch)
                except BaseException as exc:
                    for mutation in batch:
                        if not mutation.future.done():
                            mutation.future.set_exception(exc)
                    continue
                for mutation in batch:
                    if mutation.future.done():
                        continue
                    result = (
                        mutation.effect_id
                        if isinstance(mutation, _PreparedEffectMutation)
                        else None
                    )
                    mutation.future.set_result(result)
        finally:
            current = asyncio.current_task()
            if self._effect_flush_tasks.get(tenant_id) is current:
                self._effect_flush_tasks.pop(tenant_id, None)

    async def _enqueue_prepared_effect(self, mutation: _PreparedEffectMutation) -> str:
        result = await self._enqueue_effect_mutation(mutation)
        return str(result)

    @staticmethod
    def _render_gate6_rows(
        previous: str, batch: list[_Gate6Mutation]
    ) -> list[tuple[_Gate6Mutation, dict[str, Any], str, str]]:
        rows: list[tuple[_Gate6Mutation, dict[str, Any], str, str]] = []
        for mutation in batch:
            value = dict(mutation.record)
            value['gen_ai.evidence.hash_prev'] = previous
            record_hash = hashlib.sha256(canonical_json(value)).hexdigest()
            value['record_hash'] = record_hash
            if mutation.signer is not None:
                signature = mutation.signer(canonical_json(value))
                if not isinstance(signature, str) or not signature:
                    raise ConflictError('Gate6 signer returned an invalid signature')
                value['signature'] = signature
            rows.append((mutation, value, previous, record_hash))
            previous = record_hash
        return rows

    async def _enqueue_prepared_effect_audit(
        self, mutation: _PreparedEffectAuditMutation
    ) -> str:
        tenant_id = mutation.effect.tenant_id
        self._prepared_audit_batches.setdefault(tenant_id, []).append(mutation)
        task = self._effect_audit_tasks.get(tenant_id)
        if task is None or task.done():
            self._effect_audit_tasks[tenant_id] = asyncio.create_task(
                self._flush_effect_audits(tenant_id)
            )
        return str(await asyncio.shield(mutation.effect.future))

    async def _flush_effect_audits(self, tenant_id: str) -> None:
        try:
            await asyncio.sleep(0.002)
            while True:
                final_batch = self._final_batches.pop(tenant_id, [])
                prepared_batch = self._prepared_audit_batches.pop(tenant_id, [])
                if not final_batch and not prepared_batch:
                    return
                if final_batch:
                    try:
                        final_completed = (
                            await self._persist_final_effect_audits_retry(
                                tenant_id, final_batch
                            )
                        )
                    except BaseException as exc:
                        for item in final_batch:
                            if not item.effect.future.done():
                                item.effect.future.cancel()
                            if not item.gate6.future.done():
                                item.gate6.future.set_exception(exc)
                    else:
                        for item in final_batch:
                            if not item.effect.future.done():
                                item.effect.future.set_result(None)
                        for gate6, result in final_completed:
                            if not gate6.future.done():
                                gate6.future.set_result(result)
                if prepared_batch:
                    try:
                        prepared_completed = (
                            await self._persist_prepared_effect_audits_retry(
                                tenant_id, prepared_batch
                            )
                        )
                    except BaseException as exc:
                        for item in prepared_batch:
                            if not item.effect.future.done():
                                item.effect.future.set_exception(exc)
                            if not item.gate6.future.done():
                                item.gate6.future.cancel()
                    else:
                        for item in prepared_batch:
                            if not item.effect.future.done():
                                item.effect.future.set_result(item.effect.effect_id)
                        for gate6, result in prepared_completed:
                            if not gate6.future.done():
                                gate6.future.set_result(result)
                if (
                    not self._final_batches.get(tenant_id)
                    and not self._prepared_audit_batches.get(tenant_id)
                ):
                    await asyncio.sleep(0.002)
        finally:
            current = asyncio.current_task()
            if self._effect_audit_tasks.get(tenant_id) is current:
                self._effect_audit_tasks.pop(tenant_id, None)

    async def _persist_prepared_effect_audits_retry(
        self, tenant_id: str, batch: list[_PreparedEffectAuditMutation]
    ) -> list[tuple[_Gate6Mutation, dict[str, Any]]]:
        try:
            return await self._persist_prepared_effect_audits_cte(tenant_id, batch)
        except _ChainTailConflict:
            return await self._persist_prepared_effect_audits_cte(tenant_id, batch)

    async def _persist_prepared_effect_audits_cte(
        self, tenant_id: str, batch: list[_PreparedEffectAuditMutation]
    ) -> list[tuple[_Gate6Mutation, dict[str, Any]]]:
        async with self._effect_gate6_connection(tenant_id) as conn:
            effect_previous, gate_previous = await self._cached_tail_pair(
                conn, tenant_id
            )
            effect_expected = effect_previous
            gate_expected = gate_previous
            effects = [dict(zip(
                (
                    'effect_id','tenant_id','trace_id','principal_sub',
                    'principal_username','agent_id','data_domain','tool_name',
                    'args_sha256','contract_version','contract_hash',
                    'contract_snapshot','side_effect_level','reversibility',
                    'undo_window_seconds','lease_owner','authorization_snapshot',
                ),
                item.effect.insert_args,
            )) for item in batch]
            effect_events = []
            for item in batch:
                effect = item.effect
                payload = {'trace_id': effect.trace_id}
                value = {
                    'tenant_id': tenant_id,
                    'effect_id': effect.effect_id,
                    'event_type': 'effect_prepared',
                    'actor_sub': effect.actor,
                    'payload': payload,
                    'prev_hash': effect_previous,
                }
                record_hash = sha256_json(value)
                effect_events.append({**value, 'record_hash': record_hash})
                effect_previous = record_hash
            gate_rows = self._render_gate6_rows(
                gate_previous, [item.gate6 for item in batch]
            )
            inserted = await conn.fetch(
                self._prepared_effect_audit_cte_sql(),
                tenant_id,
                effect_expected,
                effect_previous,
                gate_expected,
                gate_rows[-1][3],
                effects,
                effect_events,
                [item.trace_id for item, _value, _previous, _hash in gate_rows],
                [value for _item, value, _previous, _hash in gate_rows],
                [previous for _item, _value, previous, _hash in gate_rows],
                [record_hash for _item, _value, _previous, record_hash in gate_rows],
                [
                    item.source_instance or 'unknown'
                    for item, _value, _previous, _hash in gate_rows
                ],
            )
            if len(inserted) != len(batch):
                await self._refresh_tail_pair(conn, tenant_id)
                raise _ChainTailConflict('prepared Effect/Gate6 tail CAS conflict')
            self._chain_tail_cache[('effect', tenant_id)] = effect_previous
            self._chain_tail_cache[('gate6', tenant_id)] = gate_rows[-1][3]
            sequences = {str(row['record_hash']): int(row['seq']) for row in inserted}
            return [
                (item, {'seq': sequences[record_hash], 'record': value})
                for item, value, _previous, record_hash in gate_rows
            ]

    @staticmethod
    def _prepared_effect_audit_cte_sql() -> str:
        return '''
        WITH locked_tails AS MATERIALIZED (
          SELECT chain,tail_hash FROM xa_chain_tails
          WHERE tenant_id=$1 AND chain IN ('effect','gate6')
          ORDER BY chain FOR UPDATE
        ), valid_tails AS (
          SELECT 1 AS ok
          WHERE (SELECT tail_hash FROM locked_tails WHERE chain='effect')=$2
            AND (SELECT tail_hash FROM locked_tails WHERE chain='gate6')=$4
        ), updated_tails AS (
          UPDATE xa_chain_tails t
          SET tail_hash=CASE t.chain WHEN 'effect' THEN $3 ELSE $5 END,
              updated_at=now()
          FROM valid_tails v
          WHERE t.tenant_id=$1 AND t.chain IN ('effect','gate6')
          RETURNING t.chain
        ), effect_input AS (
          SELECT * FROM jsonb_to_recordset($6::jsonb) AS e(
            effect_id text,tenant_id text,trace_id text,principal_sub text,
            principal_username text,agent_id text,data_domain text,tool_name text,
            args_sha256 text,contract_version text,contract_hash text,
            contract_snapshot jsonb,side_effect_level text,reversibility text,
            undo_window_seconds integer,lease_owner text,authorization_snapshot jsonb)
        ), inserted_effects AS (
          INSERT INTO xa_effects(
            effect_id,tenant_id,trace_id,principal_sub,principal_username,
            agent_id,data_domain,tool_name,args_sha256,contract_version,
            contract_hash,contract_snapshot,side_effect_level,reversibility,
            status,undo_expires_at,lease_owner,lease_until,heartbeat_at,
            authorization_snapshot)
          SELECT effect_id,tenant_id,trace_id,principal_sub,principal_username,
            agent_id,data_domain,tool_name,args_sha256,contract_version,
            contract_hash,contract_snapshot,side_effect_level,reversibility,
            'prepared',now()+make_interval(secs=>undo_window_seconds),lease_owner,
            now()+make_interval(secs=>60),now(),authorization_snapshot
          FROM effect_input
          CROSS JOIN (SELECT count(*) AS count FROM updated_tails) d
          WHERE d.count=2
          RETURNING effect_id
        ), event_input AS (
          SELECT * FROM jsonb_to_recordset($7::jsonb) AS e(
            tenant_id text,effect_id text,event_type text,actor_sub text,
            payload jsonb,prev_hash text,record_hash text)
        ), inserted_events AS (
          INSERT INTO xa_effect_events(
            tenant_id,effect_id,event_type,actor_sub,payload,prev_hash,record_hash)
          SELECT e.tenant_id,e.effect_id,e.event_type,e.actor_sub,e.payload,
                 e.prev_hash,e.record_hash
          FROM event_input e
          CROSS JOIN (SELECT count(*) AS count FROM inserted_effects) d
          WHERE d.count=jsonb_array_length($6::jsonb)
          RETURNING seq
        ), gate_input AS (
          SELECT * FROM unnest(
            $8::text[],$9::jsonb[],$10::text[],$11::text[],$12::text[])
            WITH ORDINALITY AS g(
              trace_id,record,prev_hash,record_hash,source_instance,ordinality)
        )
        INSERT INTO xa_gate6_events(
          tenant_id,trace_id,record,prev_hash,record_hash,source_instance)
        SELECT (record->>'gen_ai.governance.tenant_id'),g.trace_id,g.record,
               g.prev_hash,g.record_hash,g.source_instance
        FROM gate_input g
        CROSS JOIN (SELECT count(*) AS count FROM inserted_events) d
        WHERE d.count=jsonb_array_length($7::jsonb)
        ORDER BY g.ordinality
        RETURNING seq,record_hash
        '''

    async def _enqueue_final_effect_audit(
        self, mutation: _FinalEffectAuditMutation
    ) -> dict[str, Any]:
        tenant_id = mutation.effect.tenant_id
        self._final_batches.setdefault(tenant_id, []).append(mutation)
        task = self._effect_audit_tasks.get(tenant_id)
        if task is None or task.done():
            self._effect_audit_tasks[tenant_id] = asyncio.create_task(
                self._flush_effect_audits(tenant_id)
            )
        return await asyncio.shield(mutation.gate6.future)

    async def _persist_final_effect_audits_retry(
        self, tenant_id: str, batch: list[_FinalEffectAuditMutation]
    ) -> list[tuple[_Gate6Mutation, dict[str, Any]]]:
        try:
            return await self._persist_final_effect_audits_cte(tenant_id, batch)
        except _ChainTailConflict:
            return await self._persist_final_effect_audits_cte(tenant_id, batch)

    async def _persist_final_effect_audits_cte(
        self, tenant_id: str, batch: list[_FinalEffectAuditMutation]
    ) -> list[tuple[_Gate6Mutation, dict[str, Any]]]:
        async with self._effect_gate6_connection(tenant_id) as conn:
            effect_previous, gate_previous = await self._cached_tail_pair(
                conn, tenant_id
            )
            effect_expected = effect_previous
            gate_expected = gate_previous
            effects = []
            effect_events = []
            for item in batch:
                effect = item.effect
                effects.append({
                    'effect_id': effect.effect_id,
                    'status': effect.status,
                    'key_id': effect.encrypted.key_id,
                    'wrapped_dek': base64.b64encode(effect.encrypted.wrapped_dek).decode(),
                    'recovery_nonce': base64.b64encode(effect.encrypted.nonce).decode(),
                    'recovery_ciphertext': base64.b64encode(
                        effect.encrypted.ciphertext
                    ).decode(),
                    'result_sha256': effect.result_sha256,
                    'downstream_reference': effect.downstream_reference,
                    'tool_name': effect.tool_name,
                    'reversibility': effect.reversibility,
                })
                event_type = (
                    'effect_available'
                    if effect.status == 'available'
                    else effect.status
                )
                payload = {'result_sha256': effect.result_sha256}
                value = {
                    'tenant_id': tenant_id,
                    'effect_id': effect.effect_id,
                    'event_type': event_type,
                    'actor_sub': effect.actor,
                    'payload': payload,
                    'prev_hash': effect_previous,
                }
                record_hash = sha256_json(value)
                effect_events.append({**value, 'record_hash': record_hash})
                effect_previous = record_hash
            gate_rows = self._render_gate6_rows(
                gate_previous, [item.gate6 for item in batch]
            )
            inserted = await conn.fetch(
                self._final_effect_audit_cte_sql(),
                tenant_id,
                effect_expected,
                effect_previous,
                gate_expected,
                gate_rows[-1][3],
                effects,
                effect_events,
                [item.trace_id for item, _value, _previous, _hash in gate_rows],
                [value for _item, value, _previous, _hash in gate_rows],
                [previous for _item, _value, previous, _hash in gate_rows],
                [record_hash for _item, _value, _previous, record_hash in gate_rows],
                [
                    item.source_instance or 'unknown'
                    for item, _value, _previous, _hash in gate_rows
                ],
            )
            if len(inserted) != len(batch):
                await self._refresh_tail_pair(conn, tenant_id)
                raise _ChainTailConflict('final Effect/Gate6 tail CAS conflict')
            self._chain_tail_cache[('effect', tenant_id)] = effect_previous
            self._chain_tail_cache[('gate6', tenant_id)] = gate_rows[-1][3]
            sequences = {str(row['record_hash']): int(row['seq']) for row in inserted}
            return [
                (item, {'seq': sequences[record_hash], 'record': value})
                for item, value, _previous, record_hash in gate_rows
            ]

    @staticmethod
    def _final_effect_audit_cte_sql() -> str:
        return '''
        WITH locked_tails AS MATERIALIZED (
          SELECT chain,tail_hash FROM xa_chain_tails
          WHERE tenant_id=$1 AND chain IN ('effect','gate6')
          ORDER BY chain FOR UPDATE
        ), valid_tails AS (
          SELECT 1 AS ok
          WHERE (SELECT tail_hash FROM locked_tails WHERE chain='effect')=$2
            AND (SELECT tail_hash FROM locked_tails WHERE chain='gate6')=$4
        ), updated_tails AS (
          UPDATE xa_chain_tails t
          SET tail_hash=CASE t.chain WHEN 'effect' THEN $3 ELSE $5 END,
              updated_at=now()
          FROM valid_tails v
          WHERE t.tenant_id=$1 AND t.chain IN ('effect','gate6')
          RETURNING t.chain
        ), effect_input AS (
          SELECT * FROM jsonb_to_recordset($6::jsonb) AS e(
            effect_id text,status text,key_id text,wrapped_dek text,
            recovery_nonce text,recovery_ciphertext text,result_sha256 text,
            downstream_reference text,tool_name text,reversibility text)
        ), updated_effects AS (
          UPDATE xa_effects AS effect
             SET status=e.status,completed_at=now(),updated_at=now(),
                 key_id=e.key_id,wrapped_dek=decode(e.wrapped_dek,'base64'),
                 recovery_nonce=decode(e.recovery_nonce,'base64'),
                 recovery_ciphertext=decode(e.recovery_ciphertext,'base64'),
                 result_sha256=e.result_sha256,
                 downstream_reference=e.downstream_reference,
                 lease_owner=NULL,lease_until=NULL,heartbeat_at=NULL
            FROM effect_input e
           WHERE effect.effect_id=e.effect_id AND effect.tenant_id=$1
             AND effect.tool_name=e.tool_name
             AND effect.reversibility=e.reversibility
             AND effect.status='prepared'
             AND (SELECT count(*) FROM updated_tails)=2
          RETURNING effect.effect_id
        ), event_input AS (
          SELECT * FROM jsonb_to_recordset($7::jsonb) AS e(
            tenant_id text,effect_id text,event_type text,actor_sub text,
            payload jsonb,prev_hash text,record_hash text)
        ), inserted_events AS (
          INSERT INTO xa_effect_events(
            tenant_id,effect_id,event_type,actor_sub,payload,prev_hash,record_hash)
          SELECT e.tenant_id,e.effect_id,e.event_type,e.actor_sub,e.payload,
                 e.prev_hash,e.record_hash
          FROM event_input e
          CROSS JOIN (SELECT count(*) AS count FROM updated_effects) d
          WHERE d.count=jsonb_array_length($6::jsonb)
          RETURNING seq
        ), gate_input AS (
          SELECT * FROM unnest(
            $8::text[],$9::jsonb[],$10::text[],$11::text[],$12::text[])
            WITH ORDINALITY AS g(
              trace_id,record,prev_hash,record_hash,source_instance,ordinality)
        )
        INSERT INTO xa_gate6_events(
          tenant_id,trace_id,record,prev_hash,record_hash,source_instance)
        SELECT $1,g.trace_id,g.record,g.prev_hash,g.record_hash,g.source_instance
        FROM gate_input g
        CROSS JOIN (SELECT count(*) AS count FROM inserted_events) d
        WHERE d.count=jsonb_array_length($7::jsonb)
        ORDER BY g.ordinality
        RETURNING seq,record_hash
        '''

    async def _enqueue_gate6(self, mutation: _Gate6Mutation) -> dict[str, Any]:
        queue = self._gate6_batches.setdefault(mutation.tenant_id, [])
        queue.append(mutation)
        if len(queue) == 1:
            decision = str(mutation.record.get("gen_ai.decision.final") or "")
            delay = 0.002 if decision == 'require_approval' else 0.001
            task = asyncio.create_task(
                self._flush_gate6_worker(mutation.tenant_id, delay)
            )
            self._gate6_workers[mutation.tenant_id] = task
            self._gate6_flush_tasks.add(task)
            task.add_done_callback(self._gate6_flush_tasks.discard)
        return await asyncio.shield(mutation.future)

    async def _flush_gate6_worker(self, tenant_id: str, delay: float) -> None:
        try:
            while self._gate6_batches.get(tenant_id):
                await self._flush_gate6(tenant_id, delay)
                queue = self._gate6_batches.get(tenant_id, [])
                if queue:
                    decision = str(
                        queue[0].record.get('gen_ai.decision.final') or ''
                    )
                    delay = 0.002 if decision == 'require_approval' else 0.001
        finally:
            current = asyncio.current_task()
            if self._gate6_workers.get(tenant_id) is current:
                self._gate6_workers.pop(tenant_id, None)

    async def _flush_gate6(self, tenant_id: str, delay: float) -> None:
        await asyncio.sleep(delay)
        batch = self._gate6_batches.pop(tenant_id, [])
        if not batch:
            return
        completed: list[tuple[_Gate6Mutation, dict[str, Any]]] = []
        try:
            async with self._chain_connection("gate6", tenant_id) as conn:
                previous = await self._lock_and_read_chain_tail(conn, "gate6", tenant_id)
                prepared: list[tuple[_Gate6Mutation, dict[str, Any], str, str]] = []
                for mutation in batch:
                    value = dict(mutation.record)
                    value["gen_ai.evidence.hash_prev"] = previous
                    record_hash = hashlib.sha256(canonical_json(value)).hexdigest()
                    value["record_hash"] = record_hash
                    if mutation.signer is not None:
                        signature = mutation.signer(canonical_json(value))
                        if not isinstance(signature, str) or not signature:
                            raise ConflictError("Gate6 signer returned an invalid signature")
                        value["signature"] = signature
                    prepared.append((mutation, value, previous, record_hash))
                    previous = record_hash
                fetch = getattr(conn, "fetch", None)
                if fetch is None:
                    for mutation, value, previous, record_hash in prepared:
                        seq = await conn.fetchval(
                            """
                            INSERT INTO xa_gate6_events(
                              tenant_id,trace_id,record,prev_hash,record_hash,source_instance)
                            VALUES($1,$2,$3::jsonb,$4,$5,$6) RETURNING seq
                            """,
                            tenant_id,
                            mutation.trace_id,
                            value,
                            previous,
                            record_hash,
                            mutation.source_instance or "unknown",
                        )
                        completed.append((mutation, {"seq": int(seq), "record": value}))
                else:
                    inserted = await fetch(
                        """
                        INSERT INTO xa_gate6_events(
                          tenant_id,trace_id,record,prev_hash,record_hash,source_instance)
                        SELECT $1,input.trace_id,input.record,input.prev_hash,input.record_hash,
                               input.source_instance
                          FROM unnest($2::text[],$3::jsonb[],$4::text[],$5::text[],$6::text[])
                               WITH ORDINALITY AS input(
                                 trace_id,record,prev_hash,record_hash,source_instance,ordinality)
                         ORDER BY input.ordinality
                        RETURNING seq,record_hash
                        """,
                        tenant_id,
                        [item[0].trace_id for item in prepared],
                        [item[1] for item in prepared],
                        [item[2] for item in prepared],
                        [item[3] for item in prepared],
                        [item[0].source_instance or "unknown" for item in prepared],
                    )
                    sequence_by_hash = {
                        str(row["record_hash"]): int(row["seq"]) for row in inserted
                    }
                    for mutation, value, _previous, record_hash in prepared:
                        completed.append(
                            (
                                mutation,
                                {"seq": sequence_by_hash[record_hash], "record": value},
                            )
                        )
                await self._write_chain_tail(
                    conn, 'gate6', tenant_id, prepared[-1][3]
                )
        except BaseException as exc:
            for mutation in batch:
                if not mutation.future.done():
                    mutation.future.set_exception(exc)
            return
        for mutation, result in completed:
            if not mutation.future.done():
                mutation.future.set_result(result)

    async def _enqueue_completed_effect(self, mutation: _CompletedEffectMutation) -> None:
        await self._enqueue_effect_mutation(mutation)

    async def connect(self) -> None:
        import asyncpg

        if self.pool is None:

            async def init_connection(conn: Any) -> None:
                for type_name in ("json", "jsonb"):
                    await conn.set_type_codec(
                        type_name,
                        schema="pg_catalog",
                        encoder=json.dumps,
                        decoder=json.loads,
                        format="text",
                    )
                commit_delay_us = max(
                    0,
                    min(100_000, int(os.getenv("XA_GUARD_DB_COMMIT_DELAY_US", "0"))),
                )
                if commit_delay_us:
                    await conn.execute(f"SET commit_delay={commit_delay_us}")
                    await conn.execute("SET commit_siblings=1")

            min_pool_size = max(1, int(os.getenv("XA_GUARD_DB_POOL_MIN_SIZE", "1")))
            max_pool_size = max(
                min_pool_size, int(os.getenv("XA_GUARD_DB_POOL_MAX_SIZE", "20"))
            )
            self.pool = await asyncpg.create_pool(
                self.dsn,
                min_size=min_pool_size,
                max_size=max_pool_size,
                command_timeout=10,
                init=init_connection,
            )

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    async def migrate(self) -> None:
        if self.pool is None:
            raise StoreError("store is not connected")
        migration_dir = Path(__file__).with_name("migrations")
        migrations = sorted(migration_dir.glob("[0-9][0-9][0-9]_*.sql"))
        async with self.pool.acquire() as conn:
            await conn.execute("SELECT pg_advisory_lock($1)", self.MIGRATION_LOCK_ID)
            try:
                await conn.execute(
                    "CREATE TABLE IF NOT EXISTS xa_schema_versions ("
                    "version integer PRIMARY KEY,name text NOT NULL,applied_at timestamptz NOT NULL DEFAULT now())"
                )
                applied = {
                    row["version"] for row in await conn.fetch("SELECT version FROM xa_schema_versions")
                }
                for path in migrations:
                    version = int(path.name.split("_", 1)[0])
                    if version in applied:
                        continue
                    async with conn.transaction():
                        await conn.execute(path.read_text(encoding="utf-8"))
                        await conn.execute(
                            "INSERT INTO xa_schema_versions(version,name) VALUES($1,$2)", version, path.name
                        )
            finally:
                await conn.execute("SELECT pg_advisory_unlock($1)", self.MIGRATION_LOCK_ID)

    async def database_ready(self) -> bool:
        try:
            if not self.pool:
                return False
            version = await self.schema_version()
            tables = await self.pool.fetchval(
                "SELECT bool_and(to_regclass(name) IS NOT NULL) FROM unnest($1::text[]) AS name",
                ["xa_effects", "xa_assignments", "xa_undo_requests", "xa_reference_tickets"],
            )
            return version >= 4 and bool(tables)
        except Exception:
            return False

    async def ready(self) -> bool:
        if not await self.database_ready() or self.key_provider is None:
            return False
        try:
            return await self.key_provider.ready()
        except Exception:
            return False

    async def schema_version(self) -> int:
        return int(await self.pool.fetchval("SELECT COALESCE(max(version),0) FROM xa_schema_versions"))

    async def effective_assignments(self, principal: Principal, agent_id: str = "") -> list[dict[str, Any]]:
        groups = list(principal.groups)
        rows = await self.pool.fetch(
            """
            SELECT * FROM xa_assignments
             WHERE tenant_id=$1 AND deleted_at IS NULL
               AND valid_from <= now() AND (valid_until IS NULL OR valid_until > now())
               AND (($2='' OR agent_id=$2))
               AND ((subject_type='human' AND subject_id=$3)
                    OR (subject_type='group' AND subject_id=ANY($4::text[])))
             ORDER BY agent_id, version DESC
            """,
            principal.tenant_id,
            agent_id,
            principal.subject,
            groups,
        )
        return [self._public_assignment(dict(row)) for row in rows]

    async def authorize(
        self, principal: Principal, agent_id: str, tool: str, data_domain: str
    ) -> dict[str, Any]:
        row = await self.pool.fetchrow(
            '''
            SELECT * FROM xa_assignments
             WHERE tenant_id=$1 AND deleted_at IS NULL
               AND valid_from <= now() AND (valid_until IS NULL OR valid_until > now())
               AND agent_id=$2
               AND ((subject_type='human' AND subject_id=$3)
                    OR (subject_type='group' AND subject_id=ANY($4::text[])))
               AND (tools ? '*' OR tools ? $5)
               AND ($6='' OR data_domains ? '*' OR data_domains ? $6)
             ORDER BY version DESC
             LIMIT 1
            ''',
            principal.tenant_id,
            agent_id,
            principal.subject,
            list(principal.groups),
            tool,
            data_domain,
        )
        if row is not None:
            return self._public_assignment(dict(row))
        raise AuthorizationError(
            'no active assignment authorizes this agent, tool, and data domain'
        )

    async def list_assignments(self, tenant_id: str) -> list[dict[str, Any]]:
        rows = await self.pool.fetch(
            "SELECT * FROM xa_assignments WHERE tenant_id=$1 AND deleted_at IS NULL ORDER BY updated_at DESC",
            tenant_id,
        )
        return [self._public_assignment(dict(row)) for row in rows]

    async def create_assignment(self, principal: Principal, value: dict[str, Any]) -> dict[str, Any]:
        assignment_id = f"asg-{uuid.uuid4().hex}"
        try:
            row = await self.pool.fetchrow(
                """
                INSERT INTO xa_assignments(
                  assignment_id,tenant_id,subject_type,subject_id,agent_id,tools,data_domains,
                  valid_from,valid_until,changed_by)
                VALUES($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb,COALESCE($8::timestamptz,now()),$9::timestamptz,$10)
                RETURNING *
                """,
                assignment_id,
                principal.tenant_id,
                value["subject_type"],
                value["subject_id"],
                value["agent_id"],
                value["tools"],
                value["data_domains"],
                value.get("valid_from"),
                value.get("valid_until"),
                principal.subject,
            )
        except Exception as exc:
            if exc.__class__.__name__ in {"UniqueViolationError", "CheckViolationError"}:
                raise ConflictError("assignment scope already exists or validity is invalid") from exc
            raise
        result = self._public_assignment(dict(row))
        await self._control_event(
            principal.tenant_id, "assignment_created", principal.subject, assignment_id, result
        )
        return result

    async def delete_assignment(
        self, principal: Principal, assignment_id: str, expected_version: int
    ) -> None:
        row = await self.pool.fetchrow(
            """
            UPDATE xa_assignments SET deleted_at=now(),updated_at=now(),version=version+1,changed_by=$1
             WHERE assignment_id=$2 AND tenant_id=$3 AND deleted_at IS NULL AND version=$4 RETURNING *
            """,
            principal.subject,
            assignment_id,
            principal.tenant_id,
            expected_version,
        )
        if row is None:
            raise ConflictError("assignment is absent or version precondition failed")
        await self._control_event(
            principal.tenant_id,
            "assignment_deleted",
            principal.subject,
            assignment_id,
            {"previous_version": expected_version},
        )

    async def prepare_effect(
        self,
        *,
        principal: Principal,
        trace_id: str,
        data_domain: str,
        args: dict[str, Any],
        contract: EffectContractV2,
        authorization_snapshot: dict[str, Any] | None = None,
    ) -> str:
        effect_id = f"eff-{uuid.uuid4().hex}"
        snapshot = {
            "tool_name": contract.tool_name,
            "contract_version": contract.contract_version,
            "contract_hash": contract.contract_hash,
            "success_pointer": contract.success_pointer,
            "success_equals": contract.success_equals,
            "side_effect_level": contract.side_effect_level,
            "reversibility": contract.reversibility,
            "undo_window_seconds": contract.undo_window_seconds,
            "recovery_fields": contract.recovery_fields,
            "compensation_tool": contract.compensation_tool,
            "compensation_arguments": contract.compensation_arguments,
            "idempotency_header": contract.idempotency_header,
            "reconciliation_method": contract.reconciliation_method,
            "retry_delays_seconds": contract.retry_delays_seconds,
        }
        mutation = _PreparedEffectMutation(
                effect_id=effect_id,
                insert_args=(
                    effect_id,
                    principal.tenant_id,
                    trace_id,
                    principal.subject,
                    principal.username,
                    principal.agent_id,
                    data_domain,
                    contract.tool_name,
                    sha256_json(args),
                    contract.contract_version,
                    contract.contract_hash,
                    snapshot,
                    contract.side_effect_level,
                    contract.reversibility,
                    contract.undo_window_seconds,
                    f"api:{trace_id}",
                    authorization_snapshot or {},
                ),
                tenant_id=principal.tenant_id,
                actor=principal.subject,
                trace_id=trace_id,
                future=asyncio.get_running_loop().create_future(),
            )
        audit = self._staged_pre_audits.pop(trace_id, None)
        if audit is not None:
            return await self._enqueue_prepared_effect_audit(
                _PreparedEffectAuditMutation(mutation, audit)
            )
        return await self._enqueue_prepared_effect(
            mutation
        )

    async def complete_effect(
        self,
        effect_id: str,
        principal: Principal,
        recovery: dict[str, Any],
        result: Any,
        downstream_reference: str,
        *,
        expected_tool_name: str | None = None,
        expected_reversibility: str | None = None,
        defer_trace_id: str = '',
    ) -> None:
        if expected_tool_name is None or expected_reversibility is None:
            row = await self.pool.fetchrow(
                "SELECT tenant_id,tool_name,reversibility,status FROM xa_effects WHERE effect_id=$1",
                effect_id,
            )
            if row is None or row["tenant_id"] != principal.tenant_id or row["status"] != "prepared":
                raise ConflictError("effect is absent or no longer prepared")
            expected_tool_name = str(row["tool_name"])
            expected_reversibility = str(row["reversibility"])
        aad = canonical_json(
            {
                "effect_id": effect_id,
                "tenant_id": principal.tenant_id,
                "tool_name": expected_tool_name,
            }
        )
        provider = self._require_key_provider()
        with span("xa-effect-encrypt"):
            encrypted = await provider.encrypt(canonical_json(recovery), aad)
        status = "available" if expected_reversibility == "compensatable" else "manual_required"
        mutation = _CompletedEffectMutation(
                effect_id=effect_id,
                tenant_id=principal.tenant_id,
                actor=principal.subject,
                status=status,
                tool_name=expected_tool_name,
                reversibility=expected_reversibility,
                encrypted=encrypted,
                result_sha256=sha256_json(result),
                downstream_reference=downstream_reference,
                future=asyncio.get_running_loop().create_future(),
            )
        if defer_trace_id:
            if defer_trace_id in self._staged_completions:
                raise ConflictError('effect completion trace is already staged')
            self._staged_completions[defer_trace_id] = mutation
            return
        await self._enqueue_completed_effect(mutation)

    async def mark_prepared_manual(self, effect_id: str, error_code: str) -> None:
        row = await self.pool.fetchrow(
            "UPDATE xa_effects SET status='manual_required',last_error_code=$1,updated_at=now(),"
            "lease_owner=NULL,lease_until=NULL,heartbeat_at=NULL "
            "WHERE effect_id=$2 AND status='prepared' RETURNING tenant_id,principal_sub",
            error_code,
            effect_id,
        )
        if row:
            await self._effect_event(
                row["tenant_id"],
                effect_id,
                "manual_required",
                row["principal_sub"],
                {"error_code": error_code},
            )

    async def list_effects(self, tenant_id: str, limit: int = 100) -> list[dict[str, Any]]:
        rows = await self.pool.fetch(
            """
            SELECT effect_id,tenant_id,trace_id,principal_sub,principal_username,agent_id,data_domain,
              tool_name,side_effect_level,reversibility,status,prepared_at,completed_at,undo_expires_at,
              result_sha256,downstream_reference,compensation_trace_id,retry_count,last_error_code,
              authorization_snapshot
              FROM xa_effects WHERE tenant_id=$1 ORDER BY prepared_at DESC LIMIT $2
            """,
            tenant_id,
            max(1, min(limit, 200)),
        )
        return [self._json_row(dict(row)) for row in rows]

    async def get_effect(self, tenant_id: str, effect_id: str) -> dict[str, Any]:
        row = await self.pool.fetchrow(
            """
            SELECT effect_id,tenant_id,trace_id,principal_sub,principal_username,agent_id,data_domain,
              tool_name,side_effect_level,reversibility,status,prepared_at,completed_at,undo_expires_at,
              result_sha256,downstream_reference,compensation_trace_id,retry_count,last_error_code,
              authorization_snapshot
              FROM xa_effects WHERE tenant_id=$1 AND effect_id=$2
            """,
            tenant_id,
            effect_id,
        )
        if row is None:
            raise NotFoundError("effect not found")
        effect = self._json_row(dict(row))
        events = await self.pool.fetch(
            "SELECT seq,event_type,actor_sub,occurred_at,payload,prev_hash,record_hash "
            "FROM xa_effect_events WHERE tenant_id=$1 AND effect_id=$2 ORDER BY seq",
            tenant_id,
            effect_id,
        )
        effect["events"] = [self._json_row(dict(row)) for row in events]
        return effect

    async def request_undo(
        self, effect_id: str, principal: Principal, reason: str, idempotency_key: str
    ) -> tuple[dict[str, Any], bool]:
        idem = hashlib.sha256(idempotency_key.encode()).hexdigest()
        async with self.pool.acquire() as conn, conn.transaction():
            current = await conn.fetchrow(
                "SELECT request_id,status,requester_sub,reason_sha256 FROM xa_undo_requests "
                "WHERE tenant_id=$1 AND effect_id=$2 AND idempotency_sha256=$3",
                principal.tenant_id,
                effect_id,
                idem,
            )
            if current:
                reason_sha256 = hashlib.sha256(reason.encode()).hexdigest()
                if current["requester_sub"] != principal.subject or current["reason_sha256"] != reason_sha256:
                    raise ConflictError("idempotency key was replayed with different requester or parameters")
                return {"request_id": current["request_id"], "status": current["status"]}, False
            effect = await conn.fetchrow(
                "SELECT status,undo_expires_at FROM xa_effects WHERE effect_id=$1 AND tenant_id=$2 FOR UPDATE",
                effect_id,
                principal.tenant_id,
            )
            if effect is None:
                raise NotFoundError("effect not found")
            if effect["status"] != "available":
                raise ConflictError(f"effect is not undoable in status {effect['status']}")
            if effect["undo_expires_at"] <= datetime.now(timezone.utc):
                await conn.execute(
                    "UPDATE xa_effects SET status='expired',updated_at=now() WHERE effect_id=$1", effect_id
                )
                raise ConflictError("undo window has expired")
            request_id = f"undo-{uuid.uuid4().hex}"
            await conn.execute(
                """
                INSERT INTO xa_undo_requests(request_id,effect_id,tenant_id,idempotency_sha256,requester_sub,
                  requester_username,reason_sha256) VALUES($1,$2,$3,$4,$5,$6,$7)
                """,
                request_id,
                effect_id,
                principal.tenant_id,
                idem,
                principal.subject,
                principal.username,
                hashlib.sha256(reason.encode()).hexdigest(),
            )
            await conn.execute(
                "UPDATE xa_effects SET status='undo_pending',updated_at=now() WHERE effect_id=$1", effect_id
            )
            await self._effect_event_conn(
                conn,
                principal.tenant_id,
                effect_id,
                "undo_requested",
                principal.subject,
                {"request_id": request_id, "reason_sha256": hashlib.sha256(reason.encode()).hexdigest()},
            )
        return {"request_id": request_id, "status": "pending"}, True

    async def list_undo_requests(self, tenant_id: str, status: str = "pending") -> list[dict[str, Any]]:
        rows = await self.pool.fetch(
            """
            SELECT r.request_id,r.effect_id,r.tenant_id,r.requester_sub,r.requester_username,r.status,
              r.approver_sub,r.approver_username,r.requested_at,r.decided_at,e.tool_name,e.undo_expires_at
              FROM xa_undo_requests r JOIN xa_effects e ON e.effect_id=r.effect_id
             WHERE r.tenant_id=$1 AND ($2='' OR r.status=$2) ORDER BY r.requested_at
            """,
            tenant_id,
            status,
        )
        return [self._json_row(dict(row)) for row in rows]

    async def get_undo_request(self, tenant_id: str, request_id: str) -> dict[str, Any]:
        row = await self.pool.fetchrow(
            """
            SELECT r.*,e.tool_name,e.data_domain,e.agent_id,e.contract_snapshot,e.undo_expires_at,e.status AS effect_status
              FROM xa_undo_requests r JOIN xa_effects e ON e.effect_id=r.effect_id
             WHERE r.tenant_id=$1 AND r.request_id=$2
            """,
            tenant_id,
            request_id,
        )
        if row is None:
            raise NotFoundError("undo request not found")
        return self._json_row(dict(row))

    async def list_prepared(self, minimum_age_seconds: int = 5, limit: int = 20) -> list[dict[str, Any]]:
        rows = await self.pool.fetch(
            """
            SELECT * FROM xa_effects WHERE status='prepared'
              AND lease_until < now() AND prepared_at < now()-make_interval(secs=>$1)
              ORDER BY prepared_at LIMIT $2
            """,
            minimum_age_seconds,
            limit,
        )
        return [self._json_row(dict(row)) for row in rows]

    async def decide_undo(
        self,
        request_id: str,
        principal: Principal,
        decision: str,
        reason: str,
        internal_authorization: str = "",
        args_hash: str = "",
    ) -> dict[str, Any]:
        if decision not in {"approve", "reject"}:
            raise ConflictError("decision must be approve or reject")
        async with self.pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT r.*,e.undo_expires_at,e.status AS effect_status FROM xa_undo_requests r
                JOIN xa_effects e ON e.effect_id=r.effect_id
                WHERE r.request_id=$1 AND r.tenant_id=$2 FOR UPDATE OF r,e
                """,
                request_id,
                principal.tenant_id,
            )
            if row is None:
                raise NotFoundError("undo request not found")
            if row["requester_sub"] == principal.subject:
                raise AuthorizationError("separation of duty forbids self-approval")
            if row["status"] != "pending" or row["effect_status"] != "undo_pending":
                raise ConflictError("undo request was already decided")
            if row["undo_expires_at"] <= datetime.now(timezone.utc):
                await conn.execute(
                    "UPDATE xa_effects SET status='expired',updated_at=now() WHERE effect_id=$1",
                    row["effect_id"],
                )
                await conn.execute(
                    "UPDATE xa_undo_requests SET status='expired',decided_at=now() WHERE request_id=$1",
                    request_id,
                )
                raise ConflictError("undo window has expired")
            status = "approved" if decision == "approve" else "rejected"
            await conn.execute(
                """
                UPDATE xa_undo_requests SET status=$1,approver_sub=$2,approver_username=$3,
                  decision_reason_sha256=$4,internal_authorization=$5,compensation_args_sha256=$6,decided_at=now()
                 WHERE request_id=$7
                """,
                status,
                principal.subject,
                principal.username,
                hashlib.sha256(reason.encode()).hexdigest(),
                internal_authorization or None,
                args_hash,
                request_id,
            )
            await conn.execute(
                "UPDATE xa_effects SET status=$1,updated_at=now() WHERE effect_id=$2",
                status,
                row["effect_id"],
            )
            await self._effect_event_conn(
                conn,
                principal.tenant_id,
                row["effect_id"],
                f"undo_{status}",
                principal.subject,
                {"request_id": request_id},
            )
        return {"request_id": request_id, "effect_id": row["effect_id"], "status": status}

    async def claim_work(self, worker_id: str, lease_seconds: int = 60) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT e.*,r.request_id,r.approver_sub,r.internal_authorization,r.compensation_args_sha256
                  FROM xa_effects e JOIN xa_undo_requests r ON r.effect_id=e.effect_id AND r.status='approved'
                 WHERE (e.status='approved' OR (e.status='retry_wait' AND e.next_attempt_at<=now())
                    OR (e.status='compensating' AND e.lease_until<now()))
                 ORDER BY COALESCE(e.next_attempt_at,e.updated_at)
                 FOR UPDATE OF e SKIP LOCKED LIMIT 1
                """
            )
            if row is None:
                return None
            await conn.execute(
                "UPDATE xa_effects SET status='compensating',lease_owner=$1,lease_until=now()+make_interval(secs=>$2),heartbeat_at=now(),updated_at=now() WHERE effect_id=$3",
                worker_id,
                lease_seconds,
                row["effect_id"],
            )
            await self._effect_event_conn(
                conn,
                row["tenant_id"],
                row["effect_id"],
                "compensation_started",
                worker_id,
                {"request_id": row["request_id"], "lease_seconds": lease_seconds},
            )
            return self._json_row(dict(row))

    async def heartbeat(self, effect_id: str, worker_id: str, lease_seconds: int = 60) -> bool:
        changed = await self.pool.fetchval(
            "UPDATE xa_effects SET lease_until=now()+make_interval(secs=>$1),heartbeat_at=now() "
            "WHERE effect_id=$2 AND status='compensating' AND lease_owner=$3 RETURNING 1",
            lease_seconds,
            effect_id,
            worker_id,
        )
        return changed is not None

    async def decrypt_recovery(self, row: dict[str, Any]) -> dict[str, Any]:
        envelope = EncryptedEnvelope(
            key_id=row["key_id"],
            wrapped_dek=bytes(row["wrapped_dek"]),
            nonce=bytes(row["recovery_nonce"]),
            ciphertext=bytes(row["recovery_ciphertext"]),
        )
        aad = canonical_json(
            {"effect_id": row["effect_id"], "tenant_id": row["tenant_id"], "tool_name": row["tool_name"]}
        )
        provider = self._require_key_provider()
        return json.loads(await provider.decrypt(envelope, aad))

    async def complete_work(self, row: dict[str, Any], worker_id: str, trace_id: str) -> None:
        async with self.pool.acquire() as conn, conn.transaction():
            changed = await conn.fetchval(
                """
                UPDATE xa_effects SET status='compensated',compensation_trace_id=$1,lease_owner=NULL,
                  lease_until=NULL,heartbeat_at=NULL,updated_at=now() WHERE effect_id=$2 AND lease_owner=$3 RETURNING 1
                """,
                trace_id,
                row["effect_id"],
                worker_id,
            )
            if changed is None:
                raise ConflictError("worker lease was lost")
            await conn.execute(
                "UPDATE xa_undo_requests SET status='completed' WHERE request_id=$1", row["request_id"]
            )
            await self._effect_event_conn(
                conn,
                row["tenant_id"],
                row["effect_id"],
                "compensated",
                worker_id,
                {"request_id": row["request_id"], "trace_id": trace_id},
            )

    async def fail_work(self, row: dict[str, Any], worker_id: str, retryable: bool, error_code: str) -> str:
        retry_count = int(row.get("retry_count") or 0) + 1
        delays = tuple(row.get("contract_snapshot", {}).get("retry_delays_seconds") or (5, 30, 120))
        retry = retryable and retry_count <= len(delays)
        status = "retry_wait" if retry else "compensation_failed"
        delay = int(delays[retry_count - 1]) if retry else 0
        async with self.pool.acquire() as conn, conn.transaction():
            changed = await conn.fetchval(
                """
                UPDATE xa_effects SET status=$1,retry_count=$2,next_attempt_at=CASE WHEN $3>0 THEN now()+make_interval(secs=>$3) ELSE NULL END,
                  last_error_code=$4,lease_owner=NULL,lease_until=NULL,heartbeat_at=NULL,updated_at=now()
                 WHERE effect_id=$5 AND lease_owner=$6 RETURNING 1
                """,
                status,
                retry_count,
                delay,
                error_code,
                row["effect_id"],
                worker_id,
            )
            if changed is None:
                raise ConflictError("worker lease was lost before failure state could be recorded")
            if not retry:
                await conn.execute(
                    "UPDATE xa_undo_requests SET status='failed' WHERE request_id=$1", row["request_id"]
                )
            await self._effect_event_conn(
                conn,
                row["tenant_id"],
                row["effect_id"],
                status,
                worker_id,
                {"request_id": row["request_id"], "retry_count": retry_count, "error_code": error_code},
            )
        return status

    async def retry_failed(
        self,
        tenant_id: str,
        request_id: str,
        actor: str,
        internal_authorization: str,
        args_hash: str,
    ) -> None:
        if not internal_authorization or not args_hash:
            raise ConflictError("manual retry requires a renewed internal authorization")
        async with self.pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT e.effect_id,e.status AS effect_status,r.status AS request_status
                  FROM xa_effects e JOIN xa_undo_requests r ON r.effect_id=e.effect_id
                 WHERE r.request_id=$1 AND r.tenant_id=$2
                 FOR UPDATE OF e,r
                """,
                request_id,
                tenant_id,
            )
            if (
                row is None
                or row["effect_status"] != "compensation_failed"
                or row["request_status"] != "failed"
            ):
                raise ConflictError("request is not permanently failed")
            await conn.execute(
                """
                UPDATE xa_effects SET status='approved',next_attempt_at=NULL,last_error_code='',
                  lease_owner=NULL,lease_until=NULL,heartbeat_at=NULL,updated_at=now()
                 WHERE effect_id=$1
                """,
                row["effect_id"],
            )
            await conn.execute(
                """
                UPDATE xa_undo_requests SET status='approved',internal_authorization=$1,
                  compensation_args_sha256=$2 WHERE request_id=$3
                """,
                internal_authorization,
                args_hash,
                request_id,
            )
            await self._effect_event_conn(
                conn,
                tenant_id,
                row["effect_id"],
                "manual_retry_requested",
                actor,
                {
                    "request_id": request_id,
                    "authorization_sha256": hashlib.sha256(internal_authorization.encode()).hexdigest(),
                },
            )

    async def rewrap_batch(self, limit: int = 100) -> int:
        provider = self._require_key_provider()
        active_key_id = provider.active_key_id
        if not active_key_id:
            if not await provider.ready():
                raise StoreError("key provider is unavailable")
            active_key_id = provider.active_key_id
        if not active_key_id:
            raise StoreError("key provider has no active key")
        rows = await self.pool.fetch(
            "SELECT effect_id,key_id,wrapped_dek,recovery_nonce,recovery_ciphertext FROM xa_effects "
            "WHERE key_id IS NOT NULL AND key_id<>$1 LIMIT $2",
            active_key_id,
            limit,
        )
        count = 0
        for row in rows:
            envelope = EncryptedEnvelope(
                row["key_id"],
                bytes(row["wrapped_dek"]),
                bytes(row["recovery_nonce"]),
                bytes(row["recovery_ciphertext"]),
            )
            updated = await provider.rewrap(envelope)
            changed = await self.pool.fetchval(
                "UPDATE xa_effects SET key_id=$1,wrapped_dek=$2,updated_at=now() "
                "WHERE effect_id=$3 AND key_id=$4 RETURNING 1",
                updated.key_id,
                updated.wrapped_dek,
                row["effect_id"],
                row["key_id"],
            )
            if changed is not None:
                count += 1
        return count

    async def append_gate6_record(
        self,
        tenant_id: str,
        trace_id: str,
        record: dict[str, Any],
        *,
        hash_algo: str = "sha256",
        source_instance: str = "",
        signer: Callable[[bytes], str] | None = None,
        defer_for_effect: bool = False,
    ) -> dict[str, Any]:
        """Append one canonical SHA-256 Gate6 record under a tenant chain lock."""

        if not tenant_id or not trace_id:
            raise ConflictError("tenant_id and trace_id are required for Gate6 persistence")
        if hash_algo.lower() != "sha256":
            raise ConflictError("PostgreSQL Gate6 persistence requires canonical SHA-256")
        if len(source_instance) > 256:
            raise ConflictError("Gate6 source instance is invalid")
        value = dict(record)
        recorded_trace = str(value.get("trace_id") or "")
        if recorded_trace and recorded_trace != trace_id:
            raise ConflictError("Gate6 record trace does not match persistence scope")
        recorded_tenant = str(value.get("gen_ai.governance.tenant_id") or "")
        if recorded_tenant and recorded_tenant != tenant_id:
            raise ConflictError("Gate6 record tenant does not match persistence scope")
        value["trace_id"] = trace_id
        value.pop("record_hash", None)
        value.pop("signature", None)
        try:
            canonical_json(value)
        except (TypeError, ValueError) as exc:
            raise ConflictError("Gate6 record is not canonical JSON") from exc

        mutation = _Gate6Mutation(
                tenant_id,
                trace_id,
                value,
                source_instance or 'unknown',
                signer,
                asyncio.get_running_loop().create_future(),
            )
        if defer_for_effect:
            if trace_id in self._staged_pre_audits:
                raise ConflictError('Gate6 trace is already staged')
            self._staged_pre_audits[trace_id] = mutation
            return {'seq': None, 'record': value, 'staged': True}
        completion = self._staged_completions.pop(trace_id, None)
        if completion is not None:
            return await self._enqueue_final_effect_audit(
                _FinalEffectAuditMutation(completion, mutation)
            )
        return await self._enqueue_gate6(
            mutation
        )

    async def fetch_gate6_records(
        self,
        tenant_id: str,
        *,
        trace_id: str = "",
        after_seq: int = 0,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        rows = await self.pool.fetch(
            """
            SELECT seq,tenant_id,trace_id,record,prev_hash,record_hash,source_instance,occurred_at
              FROM xa_gate6_events
             WHERE tenant_id=$1 AND seq>$2 AND ($3='' OR trace_id=$3)
             ORDER BY seq LIMIT $4
            """,
            tenant_id,
            max(0, after_seq),
            trace_id,
            max(1, min(limit, 10_000)),
        )
        return [self._json_row(dict(row)) for row in rows]

    async def export_gate6_jsonl(
        self,
        tenant_id: str,
        *,
        trace_id: str = "",
        after_seq: int = 0,
        limit: int = 10_000,
    ) -> str:
        rows = await self.fetch_gate6_records(tenant_id, trace_id=trace_id, after_seq=after_seq, limit=limit)
        if not rows:
            return ""
        return "".join(canonical_json(row["record"]).decode("utf-8") + "\n" for row in rows)

    def _require_key_provider(self) -> KeyProvider:
        if self.key_provider is None:
            raise StoreError("effect encryption key provider is unavailable")
        return self.key_provider

    async def _effect_event(
        self, tenant_id: str, effect_id: str, kind: str, actor: str, payload: dict[str, Any]
    ) -> None:
        async with self._chain_connection("effect", tenant_id) as conn:
            await self._effect_event_conn(conn, tenant_id, effect_id, kind, actor, payload)

    async def _effect_event_conn(
        self, conn: Any, tenant_id: str, effect_id: str, kind: str, actor: str, payload: dict[str, Any]
    ) -> None:
        await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", f"effect-chain:{tenant_id}")
        prev = (
            await conn.fetchval(
                "SELECT record_hash FROM xa_effect_events WHERE tenant_id=$1 ORDER BY seq DESC LIMIT 1",
                tenant_id,
            )
            or ""
        )
        value = {
            "tenant_id": tenant_id,
            "effect_id": effect_id,
            "event_type": kind,
            "actor_sub": actor,
            "payload": payload,
            'prev_hash': prev,
        }
        record_hash = sha256_json(value)
        await conn.execute(
            "INSERT INTO xa_effect_events(tenant_id,effect_id,event_type,actor_sub,payload,prev_hash,record_hash) VALUES($1,$2,$3,$4,$5::jsonb,$6,$7)",
            tenant_id,
            effect_id,
            kind,
            actor,
            payload,
            prev,
            record_hash,
        )
        await self._write_chain_tail(conn, 'effect', tenant_id, record_hash)

    async def _control_event(
        self, tenant_id: str, kind: str, actor: str, target_id: str, payload: dict[str, Any]
    ) -> None:
        async with self._chain_connection("control", tenant_id) as conn:
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", f"control-chain:{tenant_id}")
            prev = (
                await conn.fetchval(
                    "SELECT record_hash FROM xa_control_events WHERE tenant_id=$1 ORDER BY seq DESC LIMIT 1",
                    tenant_id,
                )
                or ""
            )
            value = {
                "tenant_id": tenant_id,
                "event_type": kind,
                "actor_sub": actor,
                "target_id": target_id,
                "payload": payload,
                "prev_hash": prev,
            }
            await conn.execute(
                "INSERT INTO xa_control_events(tenant_id,event_type,actor_sub,target_id,payload,prev_hash,record_hash) VALUES($1,$2,$3,$4,$5::jsonb,$6,$7)",
                tenant_id,
                kind,
                actor,
                target_id,
                payload,
                prev,
                sha256_json(value),
            )

    @staticmethod
    def _public_assignment(row: dict[str, Any]) -> dict[str, Any]:
        return AsyncEffectStore._json_row(
            {
                key: row[key]
                for key in (
                    "assignment_id",
                    "tenant_id",
                    "subject_type",
                    "subject_id",
                    "agent_id",
                    "tools",
                    "data_domains",
                    "valid_from",
                    "valid_until",
                    "version",
                    "changed_by",
                    "created_at",
                    "updated_at",
                )
                if key in row
            }
        )

    @staticmethod
    def _json_row(row: dict[str, Any]) -> dict[str, Any]:
        for key, value in list(row.items()):
            if isinstance(value, datetime):
                row[key] = value.isoformat()
            elif isinstance(value, tuple):
                row[key] = list(value)
        return row


async def wait_for_store(store: AsyncEffectStore, timeout_seconds: float = 60) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while True:
        try:
            await store.connect()
            return
        except Exception:
            if asyncio.get_running_loop().time() >= deadline:
                raise
            await asyncio.sleep(1)
