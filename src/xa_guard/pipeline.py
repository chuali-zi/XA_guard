"""6 关卡 pipeline 编排。

调用顺序（产品架构 §3.2）：
    inbound:  gate1 → gate2 → gate4(in) → gate3 → gate5
    [downstream tool execution]
    outbound: gate4(out) → gate6(audit)

Gate1 输入攻击立即短路；Gate2/Gate4/Gate3 属于同一轮执行前决策聚合，
先让 policy deny 覆盖 HITL require_approval，再进入 Gate5 / executor。
WARN 累积。每关卡 latency_ms 写入 GateResult，全程 trace 由 gate6 落审计。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

from xa_guard.config import XAGuardConfig
from xa_guard.gates import GateStage
from xa_guard.gates.base import Gate
from xa_guard.governance import GovernanceEnforcer
from xa_guard.types import Approval, Decision, GateContext, GateResult, RiskLevel, TaintLabel

log = logging.getLogger("xa_guard.pipeline")

ToolExecutor = Callable[[GateContext], Awaitable[object]]


def _sync_ctx_from_result(ctx: GateContext, result: GateResult) -> None:
    """把 gate result.metadata 中的 risk_level / taint 同步到 ctx。

    gate2 决定 risk_level，gate3 的 predicate 依赖 ctx.risk_level；
    gate4 决定 taint，下游同理。
    """
    rl = result.metadata.get("risk_level")
    if rl is not None:
        try:
            ctx.risk_level = RiskLevel(rl) if not isinstance(rl, RiskLevel) else rl
        except ValueError:
            pass
    tt = result.metadata.get("taint")
    if tt is not None:
        try:
            ctx.taint = TaintLabel(tt) if not isinstance(tt, TaintLabel) else tt
        except ValueError:
            pass


@dataclass
class PipelineResult:
    ctx: GateContext
    allowed: bool
    tool_result: object | None
    final_decision: Decision
    final_reason: str


class Pipeline:
    """6 关卡编排器。pipeline 不知道关卡内部细节，只按顺序串。"""

    def __init__(
        self,
        gate1: Gate,
        gate2: Gate,
        gate3: Gate,
        gate4: Gate,
        gate5: Gate,
        gate6: Gate,
        cfg: XAGuardConfig | None = None,
        governance: GovernanceEnforcer | None = None,
    ) -> None:
        self.gate1 = gate1
        self.gate2 = gate2
        self.gate3 = gate3
        self.gate4 = gate4
        self.gate5 = gate5
        self.gate6 = gate6
        self.cfg = cfg
        self.governance = governance

    def _audit(self, ctx: GateContext) -> GateResult:
        """Write Gate6 evidence and retain its metadata on the shared context."""
        result = self.gate6(ctx, GateStage.OUTBOUND)
        ctx.append(result)
        return result

    def finalize_preflight(self, ctx: GateContext) -> PipelineResult:
        """Audit a domain-specific preflight without re-running generic gates.

        Supply-chain evaluators use this after appending their own GateResult so
        AIBOM's allow/warn/deny semantics are preserved while every operation
        still receives a traceable Gate6 record.
        """
        self._audit(ctx)
        return PipelineResult(
            ctx=ctx,
            allowed=ctx.final_decision not in (Decision.DENY, Decision.REQUIRE_APPROVAL),
            tool_result=None,
            final_decision=ctx.final_decision,
            final_reason=ctx.final_reason,
        )

    async def run(self, ctx: GateContext, executor: ToolExecutor) -> PipelineResult:
        """跑完整 6 关卡 + 工具执行。

        executor: 真正调用下游工具的协程函数（由 proxy.downstream 提供）。
        """
        # Protocol adapters may inject a domain-specific preflight before the
        # generic six-gate flow (for example AIBOM install admission). Preserve
        # the first blocking cause and audit it without evaluating/executing the
        # downstream path again.
        if ctx.final_decision == Decision.DENY:
            self._audit(ctx)
            return PipelineResult(
                ctx=ctx,
                allowed=False,
                tool_result=None,
                final_decision=ctx.final_decision,
                final_reason=ctx.final_reason,
            )

        if self.governance is not None and self.governance.enabled:
            result = self.governance.evaluate(ctx)
            ctx.append(result)
            if result.decision in (Decision.DENY, Decision.REQUIRE_APPROVAL):
                self._audit(ctx)
                return PipelineResult(
                    ctx=ctx,
                    allowed=False,
                    tool_result=None,
                    final_decision=ctx.final_decision,
                    final_reason=ctx.final_reason,
                )

        # ---- inbound: input firewall ----
        result = self.gate1(ctx, GateStage.INBOUND)
        _sync_ctx_from_result(ctx, result)
        ctx.append(result)
        if result.decision in (Decision.DENY, Decision.REQUIRE_APPROVAL):
            self._audit(ctx)
            return PipelineResult(
                ctx=ctx,
                allowed=False,
                tool_result=None,
                final_decision=ctx.final_decision,
                final_reason=ctx.final_reason,
            )

        # ---- inbound: risk, taint, and policy aggregation ----
        for gate in (self.gate2, self.gate4, self.gate3):
            result = gate(ctx, GateStage.INBOUND)
            _sync_ctx_from_result(ctx, result)
            ctx.append(result)

        if ctx.final_decision in (Decision.DENY, Decision.REQUIRE_APPROVAL):
            # 写一条 audit 后返回；REQUIRE_APPROVAL 同样阻断 executor。
            self._audit(ctx)
            return PipelineResult(
                ctx=ctx,
                allowed=False,
                tool_result=None,
                final_decision=ctx.final_decision,
                final_reason=ctx.final_reason,
            )

        # ---- inbound: executor sandbox ----
        result = self.gate5(ctx, GateStage.INBOUND)
        _sync_ctx_from_result(ctx, result)
        ctx.append(result)
        if result.decision in (Decision.DENY, Decision.REQUIRE_APPROVAL):
            self._audit(ctx)
            return PipelineResult(
                ctx=ctx,
                allowed=False,
                tool_result=None,
                final_decision=ctx.final_decision,
                final_reason=ctx.final_reason,
            )

        # ---- 工具执行 ----
        tool_result = None
        try:
            tool_result = await executor(ctx)
            ctx.tool_result = tool_result
        except Exception as exc:
            log.exception("downstream tool failed")
            ctx.final_decision = Decision.DENY
            ctx.final_reason = f"tool_error: {type(exc).__name__}: {exc}"
            # 仍写 audit
            self._audit(ctx)
            return PipelineResult(
                ctx=ctx,
                allowed=False,
                tool_result=None,
                final_decision=Decision.DENY,
                final_reason=ctx.final_reason,
            )

        # ---- outbound ----
        # 出向先过关卡 4（输出 taint 检查）再过关卡 6（审计）
        out_taint_result = self.gate4(ctx, GateStage.OUTBOUND)
        _sync_ctx_from_result(ctx, out_taint_result)
        ctx.append(out_taint_result)
        if out_taint_result.decision == Decision.DENY:
            ctx.tool_result = None
            tool_result = None

        self._audit(ctx)

        return PipelineResult(
            ctx=ctx,
            allowed=ctx.final_decision != Decision.DENY,
            tool_result=tool_result,
            final_decision=ctx.final_decision,
            final_reason=ctx.final_reason,
        )

    async def run_after_approval(self, ctx: GateContext, executor: ToolExecutor) -> PipelineResult:
        """Resume a REQUIRE_APPROVAL request after an explicit HITL approval.

        The pre-approval run has already executed Gate1/Gate2/Gate4/Gate3 and
        written an audit record for the blocked approval request. After approval
        we still run Gate5 before calling the tool, then Gate4(out)/Gate6.
        """
        if ctx.final_decision != Decision.REQUIRE_APPROVAL:
            return PipelineResult(
                ctx=ctx,
                allowed=ctx.final_decision != Decision.DENY,
                tool_result=ctx.tool_result,
                final_decision=ctx.final_decision,
                final_reason=ctx.final_reason,
            )

        # 审批令牌验签：令牌缺失 / 参数被改 / 签名错误 / 过期 → 拒绝执行。
        # 让 approval_token 成为真正的执行闸门，而非审计装饰字段。
        from xa_guard.approval import verify_and_consume_approval

        valid, why = verify_and_consume_approval(
            ctx.approval, trace_id=ctx.trace_id, tool_name=ctx.tool_name, arguments=ctx.arguments
        )
        if not valid:
            ctx.final_decision = Decision.DENY
            ctx.final_reason = f"approval_token_invalid: {why}"
            self._audit(ctx)
            return PipelineResult(
                ctx=ctx,
                allowed=False,
                tool_result=None,
                final_decision=ctx.final_decision,
                final_reason=ctx.final_reason,
            )

        ctx.final_decision = Decision.ALLOW
        ctx.final_reason = "hitl_approved"

        result = self.gate5(ctx, GateStage.INBOUND)
        _sync_ctx_from_result(ctx, result)
        ctx.append(result)
        if result.decision in (Decision.DENY, Decision.REQUIRE_APPROVAL):
            self._audit(ctx)
            return PipelineResult(
                ctx=ctx,
                allowed=False,
                tool_result=None,
                final_decision=ctx.final_decision,
                final_reason=ctx.final_reason,
            )

        tool_result = None
        try:
            tool_result = await executor(ctx)
            ctx.tool_result = tool_result
        except Exception as exc:
            log.exception("downstream tool failed after HITL approval")
            ctx.final_decision = Decision.DENY
            ctx.final_reason = f"tool_error: {type(exc).__name__}: {exc}"
            self._audit(ctx)
            return PipelineResult(
                ctx=ctx,
                allowed=False,
                tool_result=None,
                final_decision=Decision.DENY,
                final_reason=ctx.final_reason,
            )

        out_taint_result = self.gate4(ctx, GateStage.OUTBOUND)
        _sync_ctx_from_result(ctx, out_taint_result)
        ctx.append(out_taint_result)
        if out_taint_result.decision == Decision.DENY:
            ctx.tool_result = None
            tool_result = None

        self._audit(ctx)

        return PipelineResult(
            ctx=ctx,
            allowed=ctx.final_decision != Decision.DENY,
            tool_result=tool_result,
            final_decision=ctx.final_decision,
            final_reason=ctx.final_reason,
        )

    async def reject_after_approval(
        self,
        ctx: GateContext,
        *,
        approver: str = "",
        reason: str = "",
    ) -> PipelineResult:
        """Record an explicit HITL rejection after a REQUIRE_APPROVAL decision.

        The initial pipeline run already wrote a `require_approval` audit row.
        This method appends the operator rejection as a second `deny` row so
        audit replay can prove who rejected the request and why.
        """
        if ctx.final_decision != Decision.REQUIRE_APPROVAL:
            return PipelineResult(
                ctx=ctx,
                allowed=ctx.final_decision != Decision.DENY,
                tool_result=ctx.tool_result,
                final_decision=ctx.final_decision,
                final_reason=ctx.final_reason,
            )

        ctx.approval = Approval(
            approver=approver or "mcp-hitl-user",
            reason=reason,
        )
        ctx.tool_result = None
        ctx.final_decision = Decision.DENY
        ctx.final_reason = "hitl_rejected" if not reason else f"hitl_rejected: {reason}"
        self._audit(ctx)
        return PipelineResult(
            ctx=ctx,
            allowed=False,
            tool_result=None,
            final_decision=ctx.final_decision,
            final_reason=ctx.final_reason,
        )
