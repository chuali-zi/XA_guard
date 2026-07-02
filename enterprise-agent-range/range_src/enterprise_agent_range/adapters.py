from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any
from uuid import uuid4

from .models import CaseExecution, ToolResult
from .systems import RangeState, ToolContext, verify_audit_chain
from .tools import execute_tool


class SutAdapter(ABC):
    adapter_id: str

    @abstractmethod
    def run_case(self, case: dict[str, Any], state: RangeState) -> CaseExecution:
        raise NotImplementedError


class NullAdapter(SutAdapter):
    """No-defense baseline that executes declared mock tool steps directly."""

    adapter_id = "null_adapter"

    def run_case(self, case: dict[str, Any], state: RangeState) -> CaseExecution:
        started = time.perf_counter()
        trace_id = f"trace-{case.get('case_id', 'case')}-{uuid4().hex[:10]}"
        before_effects = len(state.side_effects)
        before_audit = len(state.audit_records)
        audit_start_hash = state.audit_prev_hash
        tool_results: list[ToolResult] = []
        infra_error: str | None = None

        try:
            for step in case.get("execution", {}).get("steps", []):
                tool_name = str(step["tool"])
                args = dict(step.get("args", {}))
                ctx = ToolContext(state=state, case=case, trace_id=trace_id)
                tool_results.append(execute_tool(ctx, tool_name, args))
        except Exception as exc:  # pragma: no cover - surfaced as evidence.
            infra_error = f"{type(exc).__name__}: {exc}"

        latency_ms = int((time.perf_counter() - started) * 1000)
        side_effects = state.side_effects[before_effects:]
        audit_records = state.audit_records[before_audit:]
        actual = build_actual(tool_results, side_effects, audit_records, infra_error, audit_start_hash, case)
        return CaseExecution(
            case=case,
            trace_id=trace_id,
            actual=actual,
            tool_results=tool_results,
            side_effects=side_effects,
            audit_records=audit_records,
            latency_ms=latency_ms,
            infra_error=infra_error,
        )


def build_actual(
    tool_results: list[ToolResult],
    side_effects: list[dict[str, Any]],
    audit_records: list[dict[str, Any]],
    infra_error: str | None,
    audit_start_hash: str = "sha256:0",
    case: dict[str, Any] | None = None,
) -> dict[str, Any]:
    committed = [effect for effect in side_effects if effect.get("committed")]
    sensitive_hits = sorted(
        {
            hit
            for effect in committed
            for hit in effect.get("sensitive_hits", [])
        }
    )
    last_decision = "allow"
    aibom_grade = None
    audit_fixture_valid = None
    replay_consistent = None
    sandbox_contained = True
    for result in tool_results:
        output = result.output
        if "decision" in output:
            last_decision = str(output["decision"])
        if "aibom_grade" in output:
            aibom_grade = output["aibom_grade"]
        if "audit_chain_valid" in output:
            audit_fixture_valid = output["audit_chain_valid"]
        if "replay_consistent" in output:
            replay_consistent = output["replay_consistent"]
        if result.tool_name in {"exec_command", "run_ci_job"}:
            sandbox_contained = bool(output.get("executed_on_host") is False or output.get("started") is True)

    if infra_error:
        last_decision = "infra_error"

    delegation_chain = []
    if case:
        delegation_chain = list(case.get("delegation_chain", []))
        if not delegation_chain:
            delegation_chain = list(case.get("agent", {}).get("delegation_chain", []))
    original_principal_present = True
    if delegation_chain:
        original = str(case.get("principal", {}).get("principal_id", "")) if case else ""
        original_principal_present = any(
            step.get("original_principal") == original or step.get("principal_id") == original
            for step in delegation_chain
            if isinstance(step, dict)
        )

    return {
        "decision": last_decision,
        "downstream_call_count": len(committed),
        "sensitive_egress": bool(sensitive_hits),
        "sensitive_hits": sensitive_hits,
        "side_effect_sinks": sorted({effect.get("sink_type") for effect in committed}),
        "audit_record_count": len(audit_records),
        "audit_chain_valid": verify_audit_chain(audit_records, start_hash=audit_start_hash),
        "audit_start_hash": audit_start_hash,
        "audit_fixture_valid": audit_fixture_valid,
        "aibom_grade": aibom_grade,
        "replay_consistent": replay_consistent,
        "sandbox_contained": sandbox_contained,
        "tool_call_count": len(tool_results),
        "tool_names": [result.tool_name for result in tool_results],
        "delegation_depth": len(delegation_chain),
        "delegation_chain_present": bool(delegation_chain),
        "original_principal_present": original_principal_present,
    }


def get_adapter(adapter_id: str) -> SutAdapter:
    if adapter_id == "null_adapter":
        return NullAdapter()
    raise ValueError(f"unsupported adapter: {adapter_id}")
