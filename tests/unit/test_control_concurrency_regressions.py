from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from xa_guard.control.models import Principal
from xa_guard.control.store import (
    AuthorizationError,
    AsyncEffectStore,
    _ChainTailConflict,
    _PreparedEffectMutation,
)


def test_concurrent_effect_mutations_share_one_tenant_batch() -> None:
    async def exercise() -> None:
        store = AsyncEffectStore('postgresql://unused')
        persisted: list[tuple[str, list[_PreparedEffectMutation]]] = []

        async def persist(
            tenant_id: str, batch: list[_PreparedEffectMutation]
        ) -> None:
            persisted.append((tenant_id, batch))

        setattr(store, '_persist_effect_mutations', persist)
        loop = asyncio.get_running_loop()
        first = _PreparedEffectMutation(
            'eff-1', (), 'acme', 'alice', 'trace-1', loop.create_future()
        )
        second = _PreparedEffectMutation(
            'eff-2', (), 'acme', 'alice', 'trace-2', loop.create_future()
        )

        results = await asyncio.gather(
            store._enqueue_prepared_effect(first),
            store._enqueue_prepared_effect(second),
        )

        assert results == ['eff-1', 'eff-2']
        assert len(persisted) == 1
        assert persisted[0][0] == 'acme'
        assert [item.effect_id for item in persisted[0][1]] == ['eff-1', 'eff-2']

    asyncio.run(exercise())


def test_chain_tail_cas_retries_once_after_a_stale_cache_conflict() -> None:
    async def exercise() -> None:
        store = AsyncEffectStore('postgresql://unused')
        calls = 0

        async def persist(_tenant_id: str, _batch: list[Any]) -> list[Any]:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise _ChainTailConflict('stale cache')
            return []

        setattr(store, '_persist_prepared_effect_audits_cte', persist)
        result = await store._persist_prepared_effect_audits_retry('acme', [])

        assert result == []
        assert calls == 2

    asyncio.run(exercise())


def test_atomic_effect_gate6_ctes_lock_and_advance_both_chain_tails() -> None:
    for sql in (
        AsyncEffectStore._prepared_effect_audit_cte_sql(),
        AsyncEffectStore._final_effect_audit_cte_sql(),
    ):
        compact = ' '.join(sql.split())
        assert 'FROM xa_chain_tails' in compact
        assert 'ORDER BY chain FOR UPDATE' in compact
        assert 'UPDATE xa_chain_tails' in compact
        assert 'WHEN \'effect\' THEN $3 ELSE $5 END' in compact
        assert 'chain IN (\'effect\',\'gate6\')' in compact
        assert 'WITH ORDINALITY AS g' in compact
        assert 'jsonb_to_recordset($8::jsonb)' not in compact
        assert 'RETURNING seq,record_hash' in compact


def test_authorize_filters_tool_and_domain_inside_postgresql() -> None:
    class Pool:
        def __init__(self, row: dict[str, Any] | None) -> None:
            self.row = row
            self.query = ''
            self.args: tuple[Any, ...] = ()

        async def fetchrow(self, query: str, *args: Any) -> dict[str, Any] | None:
            self.query = ' '.join(query.split())
            self.args = args
            return self.row

    principal = Principal(
        subject='alice-id',
        username='alice',
        tenant_id='acme',
        agent_id='general-office-agent',
        issuer='https://id.example',
        token_id_hash='token-hash',
        groups=('engineering',),
    )
    pool = Pool(
        {
            'assignment_id': 'asg-1',
            'tenant_id': 'acme',
            'tools': ['business_submit_ticket'],
            'data_domains': ['engineering_docs'],
        }
    )
    store = AsyncEffectStore('postgresql://unused')
    store.pool = pool

    assignment = asyncio.run(
        store.authorize(
            principal,
            'general-office-agent',
            'business_submit_ticket',
            'engineering_docs',
        )
    )

    assert assignment['assignment_id'] == 'asg-1'
    assert 'tools ? \'*\'' in pool.query
    assert 'data_domains ? $6' in pool.query
    assert pool.args == (
        'acme',
        'general-office-agent',
        'alice-id',
        ['engineering'],
        'business_submit_ticket',
        'engineering_docs',
    )

    store.pool = Pool(None)
    with pytest.raises(AuthorizationError):
        asyncio.run(
            store.authorize(
                principal,
                'general-office-agent',
                'business_submit_ticket',
                'engineering_docs',
            )
        )


def test_chain_tail_migration_initializes_latest_effect_and_gate6_hashes() -> None:
    migration = Path(
        'src/xa_guard/control/migrations/007_chain_tail_cas.sql'
    ).read_text(encoding='utf-8')
    compact = ' '.join(migration.split())

    assert 'CREATE TABLE IF NOT EXISTS xa_chain_tails' in compact
    assert 'PRIMARY KEY (chain, tenant_id)' in compact
    assert 'FROM xa_effect_events' in compact
    assert 'FROM xa_gate6_events' in compact
    assert compact.count('ORDER BY tenant_id, seq DESC') == 2
    assert compact.count('ON CONFLICT (chain, tenant_id) DO UPDATE') == 2


def test_gate6_lz4_migration_preserves_extended_jsonb_storage() -> None:
    migration = Path(
        'src/xa_guard/control/migrations/008_gate6_lz4.sql'
    ).read_text(encoding='utf-8')
    compact = ' '.join(migration.split())

    assert 'ALTER COLUMN record SET STORAGE EXTENDED' in compact
    assert 'ALTER COLUMN record SET COMPRESSION lz4' in compact
