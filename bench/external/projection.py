from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any, Iterable

from bench.external.provenance import record_sha256
from xa_guard.config import GateConfig, XAGuardConfig
from xa_guard.server import build_pipeline
from xa_guard.types import Decision, GateContext, InputSource


async def _run_projection_async(
    records: list[dict[str, Any]],
    *,
    audit_dir: Path,
    config_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    cfg = XAGuardConfig.from_yaml(config_path) if config_path else XAGuardConfig()
    cfg.gates["gate6"] = GateConfig(
        enabled=True,
        options={**cfg.gate("gate6").options, "audit_dir": str(audit_dir)},
    )
    pipeline = build_pipeline(cfg)

    results: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        started = time.perf_counter()
        projection = record.get("xa_guard_projection", {}) or {}
        payload = projection.get("input_payload", {}) or {}
        tool_name = str(payload.get("tool_name") or "external_benchmark_case")
        arguments = dict(payload.get("arguments") or {})
        raw_sources = payload.get("input_sources") or ["user"]
        input_sources = []
        for source in raw_sources:
            try:
                input_sources.append(InputSource(str(source)))
            except ValueError:
                input_sources.append(InputSource.USER)

        ctx = GateContext(
            tool_name=tool_name,
            arguments=arguments,
            user_role=str(payload.get("user_role") or "user"),
            session_history=list(payload.get("session_history") or []),
            input_sources=input_sources or [InputSource.USER],
        )

        async def _mock_executor(c: GateContext) -> dict[str, Any]:
            return {
                "mocked": True,
                "record_index": index,
                "tool": c.tool_name,
            }

        await pipeline.run(ctx, _mock_executor)
        latency_ms = (time.perf_counter() - started) * 1000
        audit_hash = ""
        audit_path = ""
        for gate_result in reversed(ctx.gate_results):
            if gate_result.gate_name in ("gate6_audit", "gate6"):
                audit_hash = str(gate_result.metadata.get("record_hash") or "")
                audit_path = str(gate_result.metadata.get("audit_path") or "")
                break

        expected = projection.get("expected_decision")
        expected_decision = None
        if expected:
            try:
                expected_decision = Decision(str(expected))
            except ValueError:
                expected_decision = None
        results.append(
            {
                "record_index": index,
                "benchmark": record.get("benchmark", {}).get("name"),
                "case_id": record.get("case", {}).get("case_id"),
                "normalized_record_sha256": record_sha256(record),
                "tool_name": tool_name,
                "arguments": arguments,
                "mapping_confidence": projection.get("mapping_confidence"),
                "expected_decision": expected,
                "xa_guard_decision": ctx.final_decision.value,
                "matches_expected_decision": (
                    ctx.final_decision == expected_decision if expected_decision else None
                ),
                "final_reason": ctx.final_reason,
                "rule_hits": list(ctx.rule_hits),
                "risk_level": ctx.risk_level.value,
                "taint": ctx.taint.value,
                "latency_ms": latency_ms,
                "audit_written": bool(audit_hash),
                "audit_record_hash": audit_hash,
                "audit_path": audit_path,
                "metric_scope": "xa_guard_projection_only_not_official_benchmark_score",
            }
        )
    return results


def run_projection(
    records: Iterable[dict[str, Any]],
    *,
    audit_dir: str | Path,
    config_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Run normalized external records through XA-Guard as supporting evidence."""
    return asyncio.run(
        _run_projection_async(
            list(records),
            audit_dir=Path(audit_dir),
            config_path=config_path,
        )
    )
