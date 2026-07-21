"""PostgreSQL-backed Gate6 sink for multi-replica control-plane deployments."""

from __future__ import annotations

import socket
import time
from typing import Any

from xa_guard.config import GateConfig
from xa_guard.gates.base import GateStage
from xa_guard.gates.gate6_audit import Gate6Audit
from xa_guard.types import Decision, GateContext, GateResult
from xa_guard.control.timing import span


class PostgresGate6Audit(Gate6Audit):
    """Persist the canonical Gate6 record through ``AsyncEffectStore``.

    The store owns the PostgreSQL transaction, tenant advisory lock, previous
    hash lookup, hash calculation, optional signature, and insert.  Keeping the
    whole append operation in one transaction makes a shared chain safe across
    API and Worker replicas.
    """

    def __init__(
        self,
        cfg: GateConfig,
        store: Any,
        *,
        source_instance: str = "",
    ) -> None:
        super().__init__(cfg)
        self.store = store
        self.source_instance = source_instance or socket.gethostname()

    def evaluate(
        self, ctx: GateContext, stage: GateStage = GateStage.OUTBOUND
    ) -> GateResult:
        raise RuntimeError("PostgreSQL Gate6 requires the asynchronous pipeline path")

    async def evaluate_async(
        self, ctx: GateContext, stage: GateStage = GateStage.OUTBOUND
    ) -> GateResult:
        if not self.enabled:
            return GateResult(gate_name=self.name, decision=Decision.ALLOW, note="disabled")
        if stage not in self.supported_stages:
            return GateResult(
                gate_name=self.name,
                decision=Decision.ALLOW,
                note=f"stage {stage} skipped",
            )
        started = time.perf_counter()
        record, signer, faithfulness = self.render_record(ctx)
        persistence_options: dict[str, Any] = {}
        if (
            ctx.defer_gate6_until_effect
            and ctx.final_decision == Decision.REQUIRE_APPROVAL
        ):
            persistence_options['defer_for_effect'] = True
        with span("xa-gate6-persist"):
            persisted = await self.store.append_gate6_record(
                tenant_id=ctx.tenant_id or "__system__",
                trace_id=ctx.trace_id,
                record=record,
                hash_algo=self.hash_algo,
                source_instance=self.source_instance,
                signer=signer,
                **persistence_options,
            )
        appended = dict(persisted.get("record") or persisted)
        sequence = persisted.get("seq")
        result = self.result_for_appended(
            appended,
            faithfulness,
            backend="postgresql",
            location="postgresql:xa_gate6_events",
            sequence=int(sequence) if sequence is not None else None,
        )
        result.latency_ms = (time.perf_counter() - started) * 1000
        return result
