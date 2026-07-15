from __future__ import annotations

import asyncio
from typing import Any

from xa_guard.audit.merkle import canonical_json, compute_record_hash
from xa_guard.config import GateConfig
from xa_guard.control.audit import PostgresGate6Audit
from xa_guard.gates.base import GateStage
from xa_guard.types import Decision, GateContext


class _AuditStore:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    async def append_gate6_record(
        self,
        *,
        tenant_id: str,
        trace_id: str,
        record: dict[str, Any],
        hash_algo: str,
        source_instance: str,
        signer=None,
    ) -> dict[str, Any]:
        appended = dict(record)
        appended["gen_ai.evidence.hash_prev"] = (
            self.records[-1]["record_hash"] if self.records else ""
        )
        appended["record_hash"] = compute_record_hash(appended, hash_algo)
        if signer is not None:
            appended["signature"] = signer(canonical_json(appended))
        self.records.append(appended)
        assert tenant_id == "acme-corp"
        assert trace_id == appended["trace_id"]
        assert source_instance == "api-1"
        return {"seq": len(self.records), "record": appended}


def _context(index: int) -> GateContext:
    return GateContext(
        trace_id=f"trace-{index}",
        tool_name="business_submit_ticket",
        arguments={"title": f"ticket-{index}"},
        tenant_id="acme-corp",
        human_principal="human-sub",
        agent_id="general-office-agent",
        data_domain="engineering_docs",
        identity_verified=True,
        final_decision=Decision.ALLOW,
        final_reason="allowed",
    )


def test_postgres_gate6_uses_shared_store_chain(tmp_path) -> None:
    store = _AuditStore()
    gate = PostgresGate6Audit(
        GateConfig(
            enabled=True,
            options={"audit_dir": str(tmp_path), "hash_algo": "sha256"},
        ),
        store,
        source_instance="api-1",
    )

    first = asyncio.run(gate.evaluate_async(_context(1), GateStage.OUTBOUND))
    second = asyncio.run(gate.evaluate_async(_context(2), GateStage.OUTBOUND))

    assert first.metadata["audit_backend"] == "postgresql"
    assert first.metadata["audit_sequence"] == 1
    assert second.metadata["audit_sequence"] == 2
    assert store.records[1]["gen_ai.evidence.hash_prev"] == store.records[0]["record_hash"]
    assert not (tmp_path / "audit.jsonl").exists()


def test_postgres_gate6_disabled_does_not_touch_store(tmp_path) -> None:
    store = _AuditStore()
    gate = PostgresGate6Audit(
        GateConfig(enabled=False, options={"audit_dir": str(tmp_path)}),
        store,
    )

    result = asyncio.run(gate.evaluate_async(_context(1)))

    assert result.note == "disabled"
    assert store.records == []
