from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Any

from xa_guard.control.crypto import Keyring, canonical_json
from xa_guard.control.models import EffectContractV2, Principal
from xa_guard.control.store import AsyncEffectStore


class _Transaction:
    def __init__(self, connection: "_Connection") -> None:
        self.connection = connection

    async def __aenter__(self) -> None:
        self.connection.transactions += 1

    async def __aexit__(self, *_args: Any) -> None:
        return None


class _Connection:
    def __init__(self, previous: str = "") -> None:
        self.previous = previous
        self.transactions = 0
        self.executions: list[tuple[str, tuple[Any, ...]]] = []
        self.inserted_record: dict[str, Any] | None = None

    def transaction(self) -> _Transaction:
        return _Transaction(self)

    async def execute(self, query: str, *args: Any) -> None:
        self.executions.append((" ".join(query.split()), args))

    async def fetchval(self, query: str, *args: Any) -> Any:
        compact = " ".join(query.split())
        if "SELECT record_hash FROM xa_gate6_events" in compact:
            return self.previous
        if "SELECT record_hash FROM xa_effect_events" in compact:
            return ""
        if "INSERT INTO xa_gate6_events" in compact:
            self.inserted_record = args[2]
            return 17
        return 1


class _Acquire:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    async def __aenter__(self) -> _Connection:
        return self.connection

    async def __aexit__(self, *_args: Any) -> None:
        return None


class _Pool:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection
        self.rows: list[dict[str, Any]] = []

    def acquire(self) -> _Acquire:
        return _Acquire(self.connection)

    async def fetch(self, *_args: Any) -> list[dict[str, Any]]:
        return self.rows


def _store(connection: _Connection) -> AsyncEffectStore:
    store = AsyncEffectStore(
        "postgresql://unused", Keyring({"v1": b"k" * 32}, "v1")
    )
    store.pool = _Pool(connection)
    return store


def test_gate6_append_hashes_and_signs_under_one_tenant_transaction() -> None:
    connection = _Connection(previous="previous-hash")
    store = _store(connection)
    signed_payloads: list[bytes] = []

    def signer(payload: bytes) -> str:
        signed_payloads.append(payload)
        return "external-signature"

    result = asyncio.run(
        store.append_gate6_record(
            "acme",
            "trace-1",
            {
                "trace_id": "trace-1",
                "gen_ai.governance.tenant_id": "acme",
                "gen_ai.tool.name": "business_submit_ticket",
                "record_hash": "caller-must-not-control-this",
                "signature": "caller-must-not-control-this",
            },
            source_instance="api-1",
            signer=signer,
        )
    )

    record = result["record"]
    assert result["seq"] == 17
    assert connection.transactions == 1
    assert record["gen_ai.evidence.hash_prev"] == "previous-hash"
    assert record["signature"] == "external-signature"
    unsigned = {
        key: value
        for key, value in record.items()
        if key not in {"record_hash", "signature"}
    }
    assert record["record_hash"] == hashlib.sha256(canonical_json(unsigned)).hexdigest()
    assert signed_payloads == [canonical_json({**unsigned, "record_hash": record["record_hash"]})]
    assert connection.inserted_record == record
    assert any("pg_advisory_xact_lock" in query for query, _ in connection.executions)


def test_gate6_fetch_and_jsonl_export_remain_tenant_scoped() -> None:
    connection = _Connection()
    store = _store(connection)
    store.pool.rows = [
        {
            "seq": 1,
            "tenant_id": "acme",
            "trace_id": "trace-1",
            "record": {"trace_id": "trace-1", "record_hash": "hash-1"},
            "prev_hash": "",
            "record_hash": "hash-1",
            "source_instance": "api-1",
            "occurred_at": "2026-07-12T00:00:00Z",
        }
    ]

    rows = asyncio.run(store.fetch_gate6_records("acme", trace_id="trace-1"))
    exported = asyncio.run(store.export_gate6_jsonl("acme", trace_id="trace-1"))

    assert rows[0]["tenant_id"] == "acme"
    assert exported == '{"record_hash":"hash-1","trace_id":"trace-1"}\n'


def test_prepare_effect_persists_optional_authorization_snapshot() -> None:
    connection = _Connection()
    store = _store(connection)
    principal = Principal(
        subject="alice-id",
        username="alice",
        tenant_id="acme",
        agent_id="general-office-agent",
        issuer="https://id.example",
        token_id_hash="token-hash",
    )
    contract = EffectContractV2(
        tool_name="business_submit_ticket",
        contract_version="2",
        contract_hash="contract-hash",
        success_pointer="$.ok",
        success_equals=True,
        side_effect_level="write",
        reversibility="compensatable",
        undo_window_seconds=3600,
    )
    snapshot = {"assignment_id": "asg-1", "assignment_version": 3}

    effect_id = asyncio.run(
        store.prepare_effect(
            principal=principal,
            trace_id="trace-1",
            data_domain="engineering_docs",
            args={"title": "ticket"},
            contract=contract,
            authorization_snapshot=snapshot,
        )
    )

    insert_query, insert_args = connection.executions[0]
    assert effect_id.startswith("eff-")
    assert "authorization_snapshot" in insert_query
    assert insert_args[-1] == snapshot


def test_migration_004_contains_authorization_snapshot_and_gate6_indexes() -> None:
    migration = Path(
        "src/xa_guard/control/migrations/004_external_keys_and_gate6.sql"
    ).read_text(encoding="utf-8")
    assert "authorization_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb" in migration
    assert "CREATE TABLE IF NOT EXISTS xa_gate6_events" in migration
    assert "source_instance text NOT NULL" in migration
    assert "xa_gate6_events_tenant_trace" in migration
