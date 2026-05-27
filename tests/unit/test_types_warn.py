"""Unit tests for GateContext.append() WARN decision handling."""
from __future__ import annotations

from xa_guard.types import Decision, GateContext, GateResult


def _warn_result(gate_name: str = "gate_test") -> GateResult:
    return GateResult(gate_name=gate_name, decision=Decision.WARN)


def _deny_result(gate_name: str = "gate_test") -> GateResult:
    return GateResult(gate_name=gate_name, decision=Decision.DENY, risks=["test risk"])


def test_warn_sets_final_decision():
    """WARN gate should set final_decision to WARN and final_reason contains 'warned'."""
    ctx = GateContext()
    ctx.append(_warn_result("gate_warn"))
    assert ctx.final_decision == Decision.WARN
    assert "warned" in ctx.final_reason


def test_deny_after_warn_wins():
    """DENY appended after WARN should override: final_decision becomes DENY."""
    ctx = GateContext()
    ctx.append(_warn_result("gate_warn"))
    ctx.append(_deny_result("gate_deny"))
    assert ctx.final_decision == Decision.DENY


def test_warn_does_not_downgrade_deny():
    """WARN appended after DENY must not downgrade final_decision to WARN."""
    ctx = GateContext()
    ctx.append(_deny_result("gate_deny"))
    ctx.append(_warn_result("gate_warn"))
    assert ctx.final_decision == Decision.DENY
