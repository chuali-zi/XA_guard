"""Deterministic, replayable decision-faithfulness assessment."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from xa_guard.types import Decision, GateContext

ALGORITHM_VERSION = "xa-guard-decision-faithfulness/v1"


@dataclass(frozen=True)
class FaithfulnessAssessment:
    score: float
    algorithm: str
    evidence: dict[str, Any]


def _expected_decision(ctx: GateContext) -> tuple[Decision, str]:
    decisions = [result.decision for result in ctx.gate_results]
    if Decision.DENY in decisions:
        return Decision.DENY, "deny_gate"
    if Decision.REQUIRE_APPROVAL in decisions:
        if ctx.approval is not None:
            return Decision.ALLOW, "verified_approval_resume"
        return Decision.REQUIRE_APPROVAL, "approval_gate"
    if Decision.WARN in decisions:
        return Decision.WARN, "warn_gate"
    return Decision.ALLOW, "all_gates_allow"


def assess_decision_faithfulness(ctx: GateContext) -> FaithfulnessAssessment:
    """Score whether the recorded final decision is supported by replayable context evidence."""
    expected, basis = _expected_decision(ctx)
    decision_consistent = ctx.final_decision == expected
    gate_rule_hits = {
        rule_id
        for result in ctx.gate_results
        for rule_id in result.rule_hits
    }
    context_rule_hits = set(ctx.rule_hits)
    rules_consistent = gate_rule_hits == context_rule_hits
    reason_consistent = (
        ctx.final_decision == Decision.ALLOW
        or bool(str(ctx.final_reason or "").strip())
    )
    action_consistent = (
        ctx.tool_result is None
        if ctx.final_decision in {Decision.DENY, Decision.REQUIRE_APPROVAL}
        else True
    )
    components = {
        "decision_consistent": decision_consistent,
        "rules_consistent": rules_consistent,
        "reason_consistent": reason_consistent,
        "action_consistent": action_consistent,
    }
    weights = {
        "decision_consistent": 0.55,
        "rules_consistent": 0.20,
        "reason_consistent": 0.15,
        "action_consistent": 0.10,
    }
    score = round(
        sum(weights[name] for name, passed in components.items() if passed),
        6,
    )
    return FaithfulnessAssessment(
        score=score,
        algorithm=ALGORITHM_VERSION,
        evidence={
            "basis": basis,
            "expected_decision": expected.value,
            "recorded_decision": ctx.final_decision.value,
            "components": components,
            "weights": weights,
            "gate_result_count": len(ctx.gate_results),
            "gate_rule_hit_count": len(gate_rule_hits),
            "context_rule_hit_count": len(context_rule_hits),
        },
    )
