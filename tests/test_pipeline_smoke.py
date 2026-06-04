"""pipeline 烟雾测试 — 验证 6 关卡 stub 全部能跑通。"""
import asyncio

from xa_guard.approval import issue_approval
from xa_guard.config import XAGuardConfig
from xa_guard.gates.gate1_input import Gate1Input
from xa_guard.gates.gate2_plan import Gate2Plan
from xa_guard.gates.gate3_policy import Gate3Policy
from xa_guard.gates.gate4_taint import Gate4Taint
from xa_guard.gates.gate5_sandbox import Gate5Sandbox
from xa_guard.gates.gate6_audit import Gate6Audit
from xa_guard.gates.base import Gate, GateStage
from xa_guard.pipeline import Pipeline
from xa_guard.types import Decision, GateContext, GateResult, TaintLabel


class _PipelineOrderGate(Gate):
    supported_stages = (GateStage.INBOUND, GateStage.OUTBOUND)

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


class _ApprovalGate(Gate):
    """Inbound gate that returns REQUIRE_APPROVAL to test pipeline short-circuit."""

    def __init__(self, name, calls):
        super().__init__()
        self.name = name
        self.calls = calls

    def evaluate(self, ctx, stage):
        self.calls.append(self.name)
        return GateResult(
            gate_name=self.name,
            decision=Decision.REQUIRE_APPROVAL,
            risks=["needs human approval"],
        )


class _DenyGate(Gate):
    """Inbound gate that returns DENY to test decision aggregation precedence."""

    def __init__(self, name, calls):
        super().__init__()
        self.name = name
        self.calls = calls

    def evaluate(self, ctx, stage):
        self.calls.append(self.name)
        return GateResult(
            gate_name=self.name,
            decision=Decision.DENY,
            risks=["role not allowed"],
        )


class _AuditStubGate(Gate):
    """Stub for gate6 slot — accepts both INBOUND and OUTBOUND stages."""

    supported_stages = (GateStage.INBOUND, GateStage.OUTBOUND)

    def __init__(self, name, calls):
        super().__init__()
        self.name = name
        self.calls = calls

    def evaluate(self, ctx, stage):
        self.calls.append(self.name)
        return GateResult(gate_name=self.name, decision=Decision.ALLOW)


def test_pipeline_blocks_executor_on_require_approval():
    calls = []
    executor_called = []

    pipe = Pipeline(
        gate1=_PipelineOrderGate("gate1", calls),
        gate2=_ApprovalGate("gate2", calls),
        gate3=_PipelineOrderGate("gate3", calls),
        gate4=_PipelineOrderGate("gate4", calls),
        gate5=_PipelineOrderGate("gate5", calls),
        gate6=_AuditStubGate("gate6", calls),
    )

    async def fake_executor(c):
        executor_called.append(True)
        return {"should": "not reach here"}

    ctx = GateContext(tool_name="dangerous_op")
    result = asyncio.run(pipe.run(ctx, fake_executor))

    assert result.allowed is False
    assert result.final_decision == Decision.REQUIRE_APPROVAL
    assert result.tool_result is None
    assert len(executor_called) == 0, "executor must NOT be called when REQUIRE_APPROVAL"
    assert "gate6" in calls, "gate6 audit must still run"


def test_pipeline_allows_gate3_deny_to_override_gate2_approval():
    calls = []
    executor_called = []

    pipe = Pipeline(
        gate1=_PipelineOrderGate("gate1", calls),
        gate2=_ApprovalGate("gate2", calls),
        gate3=_DenyGate("gate3", calls),
        gate4=_PipelineOrderGate("gate4", calls),
        gate5=_PipelineOrderGate("gate5", calls),
        gate6=_AuditStubGate("gate6", calls),
    )

    async def fake_executor(c):
        executor_called.append(True)
        return {"should": "not reach here"}

    ctx = GateContext(tool_name="exec_command", arguments={"cmd": "uptime"}, user_role="user")
    result = asyncio.run(pipe.run(ctx, fake_executor))

    assert result.allowed is False
    assert result.final_decision == Decision.DENY
    assert result.tool_result is None
    assert len(executor_called) == 0, "executor must NOT be called when DENY wins"
    assert calls[:4] == ["gate1", "gate2", "gate4", "gate3"]
    assert "gate5" not in calls
    assert "gate6" in calls, "gate6 audit must still run"


def test_pipeline_after_approval_runs_gate5_executor_outbound_and_audit():
    calls = []
    executor_called = []

    pipe = Pipeline(
        gate1=_PipelineOrderGate("gate1", calls),
        gate2=_ApprovalGate("gate2", calls),
        gate3=_PipelineOrderGate("gate3", calls),
        gate4=_PipelineOrderGate("gate4", calls),
        gate5=_PipelineOrderGate("gate5", calls),
        gate6=_AuditStubGate("gate6", calls),
    )

    async def fake_executor(c):
        executor_called.append(True)
        return {"ok": True}

    ctx = GateContext(tool_name="exec_command", arguments={"cmd": "uptime"}, user_role="ops")
    first = asyncio.run(pipe.run(ctx, fake_executor))
    assert first.final_decision == Decision.REQUIRE_APPROVAL
    assert executor_called == []

    # 模拟人工批准：签发审批令牌（真实流程由 proxy/upstream 在 approve 时完成）。
    ctx.approval = issue_approval(
        trace_id=ctx.trace_id, tool_name=ctx.tool_name, arguments=ctx.arguments,
        approver="ops-1", reason="smoke-approve",
    )
    resumed = asyncio.run(pipe.run_after_approval(ctx, fake_executor))

    assert resumed.allowed is True
    assert resumed.final_decision == Decision.ALLOW
    assert resumed.tool_result == {"ok": True}
    assert executor_called == [True]
    assert calls[-3:] == ["gate5", "gate4", "gate6"]
