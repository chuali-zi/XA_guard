"""pipeline 烟雾测试 — 验证 6 关卡 stub 全部能跑通。"""
import asyncio

from xa_guard.config import XAGuardConfig
from xa_guard.gates.gate1_input import Gate1Input
from xa_guard.gates.gate2_plan import Gate2Plan
from xa_guard.gates.gate3_policy import Gate3Policy
from xa_guard.gates.gate4_taint import Gate4Taint
from xa_guard.gates.gate5_sandbox import Gate5Sandbox
from xa_guard.gates.gate6_audit import Gate6Audit
from xa_guard.pipeline import Pipeline
from xa_guard.types import GateContext


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
