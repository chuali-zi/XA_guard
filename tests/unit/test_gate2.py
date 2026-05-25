"""单元测试 — Gate2Plan（关卡 2 办事大厅 HITL 审批）。"""
from __future__ import annotations

import pytest

from xa_guard.config import GateConfig
from xa_guard.gates.base import GateStage
from xa_guard.gates.gate2_plan import Gate2Plan
from xa_guard.types import Decision, GateContext, RiskLevel


RISK_FILE = "policies/tool_risks.yaml"


def _make_gate(fallback: str = "stdout") -> Gate2Plan:
    cfg = GateConfig(
        enabled=True,
        options={
            "tool_risk_file": RISK_FILE,
            "elicitation_fallback": fallback,
            "hitl_required_for": ["red"],
            "approval_token_ttl_seconds": 300,
        },
    )
    return Gate2Plan(cfg)


def _ctx(tool_name: str) -> GateContext:
    return GateContext(tool_name=tool_name, arguments={})


class TestGate2Green:
    def test_get_cpu_allow(self):
        gate = _make_gate()
        result = gate.evaluate(_ctx("get_cpu"))
        assert result.decision == Decision.ALLOW
        assert result.metadata["risk_level"] == RiskLevel.GREEN.value

    def test_read_log_allow(self):
        gate = _make_gate()
        result = gate.evaluate(_ctx("read_log"))
        assert result.decision == Decision.ALLOW
        assert result.metadata["risk_level"] == RiskLevel.GREEN.value


class TestGate2Yellow:
    def test_send_email_warn(self):
        gate = _make_gate()
        result = gate.evaluate(_ctx("send_email"))
        assert result.decision == Decision.WARN
        assert result.metadata["risk_level"] == RiskLevel.YELLOW.value
        assert result.metadata.get("notify_async") is True

    def test_restart_service_warn(self):
        gate = _make_gate()
        result = gate.evaluate(_ctx("restart_service"))
        assert result.decision == Decision.WARN
        assert result.metadata["risk_level"] == RiskLevel.YELLOW.value


class TestGate2RedFallbackStdout:
    def test_exec_command_require_approval(self, capsys):
        gate = _make_gate(fallback="stdout")
        result = gate.evaluate(_ctx("exec_command"))
        assert result.decision == Decision.REQUIRE_APPROVAL
        assert result.metadata["risk_level"] == RiskLevel.RED.value
        captured = capsys.readouterr()
        assert "APPROVAL REQUIRED" in captured.err
        assert "exec_command" in captured.err


class TestGate2RedFallbackDeny:
    def test_exec_command_deny(self):
        gate = _make_gate(fallback="deny")
        result = gate.evaluate(_ctx("exec_command"))
        assert result.decision == Decision.DENY
        assert result.metadata["risk_level"] == RiskLevel.RED.value

    def test_delete_file_deny(self):
        gate = _make_gate(fallback="deny")
        result = gate.evaluate(_ctx("delete_file"))
        assert result.decision == Decision.DENY


class TestGate2RedFallbackAsyncNotify:
    def test_exec_command_async_notify(self):
        gate = _make_gate(fallback="async_notify")
        result = gate.evaluate(_ctx("exec_command"))
        assert result.decision == Decision.WARN
        assert result.metadata.get("notify_async") is True


class TestGate2Unknown:
    def test_unknown_tool_allow(self):
        gate = _make_gate()
        result = gate.evaluate(_ctx("some_unregistered_tool"))
        assert result.decision == Decision.ALLOW
        assert result.metadata["risk_level"] == RiskLevel.GREEN.value

    def test_empty_tool_name_allow(self):
        gate = _make_gate()
        result = gate.evaluate(_ctx(""))
        assert result.decision == Decision.ALLOW


class TestGate2NoMutate:
    def test_ctx_not_mutated(self):
        gate = _make_gate(fallback="deny")
        ctx = _ctx("exec_command")
        original_risk = ctx.risk_level
        original_decision = ctx.final_decision
        gate.evaluate(ctx)
        assert ctx.risk_level == original_risk
        assert ctx.final_decision == original_decision
        assert ctx.gate_results == []


class TestGate2DisabledGate:
    def test_disabled_gate_allows_all(self):
        cfg = GateConfig(enabled=False, options={"tool_risk_file": RISK_FILE})
        gate = Gate2Plan(cfg)
        result = gate(GateContext(tool_name="exec_command"))
        assert result.decision == Decision.ALLOW
        assert result.note == "disabled"
