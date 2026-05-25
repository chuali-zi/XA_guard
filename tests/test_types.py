"""共享类型 sanity test — 子 agent 改 types.py 后跑这个。"""
from xa_guard.types import (
    AuditRecord,
    Decision,
    GateContext,
    GateResult,
    RiskLevel,
    TaintLabel,
)


def test_taint_merge():
    assert TaintLabel.PUBLIC.merge(TaintLabel.INTERNAL) == TaintLabel.INTERNAL
    assert TaintLabel.INTERNAL.merge(TaintLabel.CONFIDENTIAL) == TaintLabel.CONFIDENTIAL
    assert TaintLabel.CONFIDENTIAL.merge(TaintLabel.PUBLIC) == TaintLabel.CONFIDENTIAL


def test_taint_flow():
    assert TaintLabel.PUBLIC.can_flow_to(TaintLabel.INTERNAL)
    assert TaintLabel.PUBLIC.can_flow_to(TaintLabel.PUBLIC)
    assert not TaintLabel.CONFIDENTIAL.can_flow_to(TaintLabel.INTERNAL)
    assert not TaintLabel.CONFIDENTIAL.can_flow_to(TaintLabel.PUBLIC)


def test_gate_context_append_deny_shortcircuits_decision():
    ctx = GateContext(tool_name="exec_command")
    ctx.append(GateResult(gate_name="gate1", decision=Decision.DENY, risks=["test"]))
    assert ctx.final_decision == Decision.DENY
    assert "gate1" in ctx.final_reason


def test_audit_record_to_dict_has_otel_keys():
    rec = AuditRecord(trace_id="t", span_id="s", timestamp="2026-01-01T00:00:00Z")
    d = rec.to_dict()
    assert "gen_ai.tool.name" in d
    assert "gen_ai.evidence.hash_prev" in d


def test_risk_level_enum():
    assert RiskLevel.GREEN.value == "green"
    assert RiskLevel.RED.value == "red"
