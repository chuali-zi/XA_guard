"""pipeline 烟雾测试 — 验证 6 关卡 stub 全部能跑通。"""
import asyncio

from xa_guard.config import XAGuardConfig
from xa_guard.gates.gate1_input import Gate1Input
from xa_guard.gates.gate2_plan import Gate2Plan
from xa_guard.gates.gate3_policy import Gate3Policy
from xa_guard.gates.gate4_taint import Gate4Taint
from xa_guard.gates.gate5_sandbox import Gate5Sandbox
from xa_guard.gates.gate6_audit import Gate6Audit
from xa_guard.gates.base import Gate
from xa_guard.pipeline import Pipeline
from xa_guard.types import Decision, GateContext, GateResult, TaintLabel


class _PipelineOrderGate(Gate):
    def __init__(self, name, calls, *, metadata=None, seen_taints=None):
        super().__init__()
        self.name = name
        self.calls = calls
        self.metadata = metadata or {}
        self.seen_taints = seen_taints

    def evaluate(self, ctx, stage):
        self.calls.append(self.name)
        if self.seen_taints is not None:
            self.seen_taints[self.name] = ctx.taint
        return GateResult(
            gate_name=self.name,
            decision=Decision.ALLOW,
            metadata=self.metadata,
        )


def test_pipeline_runs_with_stubs():
    cfg = XAGuardConfig()
    pipe = Pipeline(
        gate1=Gate1Input(cfg.gate("gate1")),
        gate2=Gate2Plan(cfg.gate("gate2")),
        gate3=Gate3Policy(cfg.gate("gate3")),
        gate4=Gate4Taint(cfg.gate("gate4")),
        gate5=Gate5Sandbox(cfg.gate("gate5")),
        gate6=Gate6Audit(cfg.gate("gate6")),
        cfg=cfg,
    )

    ctx = GateContext(tool_name="get_cpu", arguments={"host": "web03"})

    async def fake_executor(c):
        return {"cpu": "30%"}

    result = asyncio.run(pipe.run(ctx, fake_executor))
    assert result.allowed is True
    # 至少跑过 6 关卡
    gate_names = [r.gate_name for r in ctx.gate_results]
    assert "gate1_input" in gate_names
    assert "gate6_audit" in gate_names


def test_pipeline_runs_gate4_before_gate3_so_policy_sees_inbound_taint():
    calls = []
    seen_taints = {}
    pipe = Pipeline(
        gate1=_PipelineOrderGate("gate1", calls),
        gate2=_PipelineOrderGate("gate2", calls),
        gate3=_PipelineOrderGate("gate3", calls, seen_taints=seen_taints),
        gate4=_PipelineOrderGate(
            "gate4",
            calls,
            metadata={"taint": TaintLabel.CONFIDENTIAL.value},
        ),
        gate5=_PipelineOrderGate("gate5", calls),
        gate6=_PipelineOrderGate("gate6", calls),
    )

    async def fake_executor(c):
        return {"ok": True}

    ctx = GateContext(tool_name="send_email")
    result = asyncio.run(pipe.run(ctx, fake_executor))

    assert result.allowed is True
    assert calls[:5] == ["gate1", "gate2", "gate4", "gate3", "gate5"]
    assert seen_taints["gate3"] == TaintLabel.CONFIDENTIAL
