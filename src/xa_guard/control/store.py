"""Async PostgreSQL assignment, effect, approval, and worker queue store."""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from xa_guard.control.crypto import EncryptedEnvelope, Keyring, canonical_json, sha256_json
from xa_guard.control.key_provider import KeyProvider, LocalKeyProvider
from xa_guard.control.models import EffectContractV2, Principal


class StoreError(RuntimeError):
    code = "store_error"


class NotFoundError(StoreError):
    code = "not_found"


class ConflictError(StoreError):
    code = "conflict"


class AuthorizationError(StoreError):
    code = "forbidden"


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

            self.pool = await asyncpg.create_pool(
                self.dsn,
                min_size=1,
                max_size=10,
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
                applied = {row["version"] for row in await conn.fetch("SELECT version FROM xa_schema_versions")}
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

    async def authorize(self, principal: Principal, agent_id: str, tool: str, data_domain: str) -> dict[str, Any]:
        rows = await self.effective_assignments(principal, agent_id)
        for row in rows:
            tools = set(row["tools"])
            domains = set(row["data_domains"])
            if ("*" in tools or tool in tools) and (not data_domain or "*" in domains or data_domain in domains):
                return row
        raise AuthorizationError("no active assignment authorizes this agent, tool, and data domain")

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
        await self._control_event(principal.tenant_id, "assignment_created", principal.subject, assignment_id, result)
        return result

    async def delete_assignment(self, principal: Principal, assignment_id: str, expected_version: int) -> None:
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
        async with self.pool.acquire() as conn, conn.transaction():
            await conn.execute(
                """
                INSERT INTO xa_effects(
                  effect_id,tenant_id,trace_id,principal_sub,principal_username,agent_id,data_domain,
                  tool_name,args_sha256,contract_version,contract_hash,contract_snapshot,side_effect_level,
                  reversibility,status,undo_expires_at,lease_owner,lease_until,heartbeat_at,
                  authorization_snapshot)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12::jsonb,$13,$14,'prepared',
                       now()+make_interval(secs=>$15),$16,now()+make_interval(secs=>60),now(),$17::jsonb)
                """,
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
            )
            await self._effect_event_conn(conn, principal.tenant_id, effect_id, "effect_prepared", principal.subject, {"trace_id": trace_id})
        return effect_id

    async def complete_effect(
        self,
        effect_id: str,
        principal: Principal,
        recovery: dict[str, Any],
        result: Any,
        downstream_reference: str,
    ) -> None:
        row = await self.pool.fetchrow(
            "SELECT tenant_id,tool_name,reversibility,status FROM xa_effects WHERE effect_id=$1", effect_id
        )
        if row is None or row["tenant_id"] != principal.tenant_id or row["status"] != "prepared":
            raise ConflictError("effect is absent or no longer prepared")
        aad = canonical_json({"effect_id": effect_id, "tenant_id": principal.tenant_id, "tool_name": row["tool_name"]})
        provider = self._require_key_provider()
        encrypted = await provider.encrypt(canonical_json(recovery), aad)
        status = "available" if row["reversibility"] == "compensatable" else "manual_required"
        async with self.pool.acquire() as conn, conn.transaction():
            changed = await conn.fetchval(
                """
                UPDATE xa_effects SET status=$1,completed_at=now(),updated_at=now(),key_id=$2,wrapped_dek=$3,
                  recovery_nonce=$4,recovery_ciphertext=$5,result_sha256=$6,downstream_reference=$7,
                  lease_owner=NULL,lease_until=NULL,heartbeat_at=NULL
                 WHERE effect_id=$8 AND status='prepared' RETURNING 1
                """,
                status,
                encrypted.key_id,
                encrypted.wrapped_dek,
                encrypted.nonce,
                encrypted.ciphertext,
                sha256_json(result),
                downstream_reference,
                effect_id,
            )
            if changed is None:
                raise ConflictError("effect is no longer prepared")
            await self._effect_event_conn(conn, principal.tenant_id, effect_id, "effect_available" if status == "available" else status, principal.subject, {"result_sha256": sha256_json(result)})

    async def mark_prepared_manual(self, effect_id: str, error_code: str) -> None:
        row = await self.pool.fetchrow(
            "UPDATE xa_effects SET status='manual_required',last_error_code=$1,updated_at=now(),"
            "lease_owner=NULL,lease_until=NULL,heartbeat_at=NULL "
            "WHERE effect_id=$2 AND status='prepared' RETURNING tenant_id,principal_sub",
            error_code,
            effect_id,
        )
        if row:
            await self._effect_event(row["tenant_id"], effect_id, "manual_required", row["principal_sub"], {"error_code": error_code})

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
                await conn.execute("UPDATE xa_effects SET status='expired',updated_at=now() WHERE effect_id=$1", effect_id)
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
            await conn.execute("UPDATE xa_effects SET status='undo_pending',updated_at=now() WHERE effect_id=$1", effect_id)
            await self._effect_event_conn(conn, principal.tenant_id, effect_id, "undo_requested", principal.subject, {"request_id": request_id, "reason_sha256": hashlib.sha256(reason.encode()).hexdigest()})
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
                await conn.execute("UPDATE xa_effects SET status='expired',updated_at=now() WHERE effect_id=$1", row["effect_id"])
                await conn.execute("UPDATE xa_undo_requests SET status='expired',decided_at=now() WHERE request_id=$1", request_id)
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
            await conn.execute("UPDATE xa_effects SET status=$1,updated_at=now() WHERE effect_id=$2", status, row["effect_id"])
            await self._effect_event_conn(conn, principal.tenant_id, row["effect_id"], f"undo_{status}", principal.subject, {"request_id": request_id})
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
            await self._effect_event_conn(conn, row["tenant_id"], row["effect_id"], "compensation_started", worker_id, {"request_id": row["request_id"], "lease_seconds": lease_seconds})
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
        aad = canonical_json({"effect_id": row["effect_id"], "tenant_id": row["tenant_id"], "tool_name": row["tool_name"]})
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
            await conn.execute("UPDATE xa_undo_requests SET status='completed' WHERE request_id=$1", row["request_id"])
            await self._effect_event_conn(conn, row["tenant_id"], row["effect_id"], "compensated", worker_id, {"request_id": row["request_id"], "trace_id": trace_id})

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
                await conn.execute("UPDATE xa_undo_requests SET status='failed' WHERE request_id=$1", row["request_id"])
            await self._effect_event_conn(conn, row["tenant_id"], row["effect_id"], status, worker_id, {"request_id": row["request_id"], "retry_count": retry_count, "error_code": error_code})
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
                    "authorization_sha256": hashlib.sha256(
                        internal_authorization.encode()
                    ).hexdigest(),
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
            envelope = EncryptedEnvelope(row["key_id"], bytes(row["wrapped_dek"]), bytes(row["recovery_nonce"]), bytes(row["recovery_ciphertext"]))
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

        async with self.pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtext($1))",
                f"gate6-chain:{tenant_id}",
            )
            previous = (
                await conn.fetchval(
                    "SELECT record_hash FROM xa_gate6_events "
                    "WHERE tenant_id=$1 ORDER BY seq DESC LIMIT 1",
                    tenant_id,
                )
                or ""
            )
            value["gen_ai.evidence.hash_prev"] = previous
            record_hash = hashlib.sha256(canonical_json(value)).hexdigest()
            value["record_hash"] = record_hash
            if signer is not None:
                signature = signer(canonical_json(value))
                if not isinstance(signature, str) or not signature:
                    raise ConflictError("Gate6 signer returned an invalid signature")
                value["signature"] = signature
            seq = await conn.fetchval(
                """
                INSERT INTO xa_gate6_events(
                  tenant_id,trace_id,record,prev_hash,record_hash,source_instance)
                VALUES($1,$2,$3::jsonb,$4,$5,$6) RETURNING seq
                """,
                tenant_id,
                trace_id,
                value,
                previous,
                record_hash,
                source_instance or "unknown",
            )
        return {"seq": int(seq), "record": value}

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
        rows = await self.fetch_gate6_records(
            tenant_id, trace_id=trace_id, after_seq=after_seq, limit=limit
        )
        if not rows:
            return ""
        return "".join(
            canonical_json(row["record"]).decode("utf-8") + "\n" for row in rows
        )

    def _require_key_provider(self) -> KeyProvider:
        if self.key_provider is None:
            raise StoreError("effect encryption key provider is unavailable")
        return self.key_provider

    async def _effect_event(self, tenant_id: str, effect_id: str, kind: str, actor: str, payload: dict[str, Any]) -> None:
        async with self.pool.acquire() as conn, conn.transaction():
            await self._effect_event_conn(conn, tenant_id, effect_id, kind, actor, payload)

    async def _effect_event_conn(self, conn: Any, tenant_id: str, effect_id: str, kind: str, actor: str, payload: dict[str, Any]) -> None:
        await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", f"effect-chain:{tenant_id}")
        prev = await conn.fetchval("SELECT record_hash FROM xa_effect_events WHERE tenant_id=$1 ORDER BY seq DESC LIMIT 1", tenant_id) or ""
        value = {"tenant_id": tenant_id, "effect_id": effect_id, "event_type": kind, "actor_sub": actor, "payload": payload, "prev_hash": prev}
        await conn.execute(
            "INSERT INTO xa_effect_events(tenant_id,effect_id,event_type,actor_sub,payload,prev_hash,record_hash) VALUES($1,$2,$3,$4,$5::jsonb,$6,$7)",
            tenant_id,
            effect_id,
            kind,
            actor,
            payload,
            prev,
            sha256_json(value),
        )

    async def _control_event(self, tenant_id: str, kind: str, actor: str, target_id: str, payload: dict[str, Any]) -> None:
        async with self.pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", f"control-chain:{tenant_id}")
            prev = await conn.fetchval("SELECT record_hash FROM xa_control_events WHERE tenant_id=$1 ORDER BY seq DESC LIMIT 1", tenant_id) or ""
            value = {"tenant_id": tenant_id, "event_type": kind, "actor_sub": actor, "target_id": target_id, "payload": payload, "prev_hash": prev}
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
        return AsyncEffectStore._json_row({
            key: row[key]
            for key in (
                "assignment_id", "tenant_id", "subject_type", "subject_id", "agent_id", "tools",
                "data_domains", "valid_from", "valid_until", "version", "changed_by", "created_at", "updated_at"
            )
            if key in row
        })

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
