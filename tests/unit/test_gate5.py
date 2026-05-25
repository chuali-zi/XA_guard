"""Gate5Sandbox 单元测试。"""
from __future__ import annotations

from xa_guard.config import GateConfig
from xa_guard.gates.base import GateStage
from xa_guard.gates.gate5_sandbox import Gate5Sandbox
from xa_guard.types import Decision, GateContext, GateResult, RiskLevel


def _ctx(risk: RiskLevel | None = None) -> GateContext:
    c = GateContext(tool_name="exec_command")
    if risk is not None:
        c.risk_level = risk
    return c


def test_gate5_disabled_returns_native():
    g = Gate5Sandbox(GateConfig(enabled=False))
    r = g(_ctx(RiskLevel.RED))  # 即便 RED，disabled 也走 native
    assert r.decision == Decision.ALLOW
    assert r.metadata["sandbox_mode"] == "native"
    assert "docker disabled in demo" in r.note


def test_gate5_routes_by_risk_level():
    g = Gate5Sandbox(GateConfig(enabled=True, options={"runtime": "runsc"}))

    r_green = g(_ctx(RiskLevel.GREEN))
    assert r_green.metadata["sandbox_mode"] == "native"

    r_yellow = g(_ctx(RiskLevel.YELLOW))
    assert r_yellow.metadata["sandbox_mode"] == "docker"

    r_red = g(_ctx(RiskLevel.RED))
    assert r_red.metadata["sandbox_mode"] == "docker_gvisor"


def test_gate5_red_degrades_when_runtime_not_gvisor():
    g = Gate5Sandbox(GateConfig(enabled=True, options={"runtime": "runc"}))
    r = g(_ctx(RiskLevel.RED))
    assert r.metadata["sandbox_mode"] == "docker"  # 降级
    assert "degrade" in r.note


def test_gate5_reads_risk_from_gate2_metadata():
    g = Gate5Sandbox(GateConfig(enabled=True, options={"runtime": "runsc"}))
    ctx = GateContext(tool_name="t")
    # 优先使用 gate2 元数据
    ctx.gate_results.append(
        GateResult(gate_name="gate2_plan", decision=Decision.ALLOW, metadata={"risk_level": "red"})
    )
    r = g(ctx)
    assert r.metadata["sandbox_mode"] == "docker_gvisor"
    assert r.metadata["risk_level"] == "red"


def test_gate5_decision_always_allow():
    """关卡 5 是路由决策性质，不应阻断。"""
    g = Gate5Sandbox(GateConfig(enabled=True))
    for level in (RiskLevel.GREEN, RiskLevel.YELLOW, RiskLevel.RED):
        r = g(_ctx(level))
        assert r.decision == Decision.ALLOW
