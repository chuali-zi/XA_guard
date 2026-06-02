"""关卡 2 · 办事大厅（HITL 审批） — 赛题方向 2。

工具调用风险等级判定：
- 从 tool_risks.yaml 加载 green/yellow/red 映射
- RED: 同步阻塞，走 elicitation fallback（stdout/deny/async_notify）
- YELLOW: 异步通知，Decision.WARN + metadata["notify_async"]=True
- GREEN: Decision.ALLOW
- 未登记工具默认 GREEN

事实源 F-3.4: 国产 IDE elicitation 全部未声明，必须 fallback。
真正 MCP elicitation 由 proxy/upstream.py 实现，本关卡只出 Decision。
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

from xa_guard.gates.base import Gate, GateStage
from xa_guard.policy.layered import get_global_source
from xa_guard.types import Decision, GateContext, GateResult, RiskLevel


def _load_tool_risks(path: str) -> dict[str, RiskLevel]:
    p = Path(path)
    if not p.is_absolute():
        p = Path(__file__).parents[3] / path
    with open(p, encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}
    mapping = raw.get("tool_risks", raw)
    return {name: RiskLevel(level.lower()) for name, level in mapping.items()}


class Gate2Plan(Gate):
    name = "gate2_plan"
    supported_stages = (GateStage.INBOUND,)

    def _load_risks(self) -> dict[str, RiskLevel]:
        """LayeredPolicySource（baseline+overlay 合并）opt-in；默认走单文件。

        prefer_layered: true 时优先 layered（生产推荐），否则保持 legacy（兼容单测）。
        """
        if bool(self.opt("prefer_layered", False)):
            layered = get_global_source()
            if layered is not None:
                risks = layered.get_tool_risks()
                if risks:
                    return risks
        risk_file = self.opt("tool_risk_file", "policies/tool_risks.yaml")
        return _load_tool_risks(risk_file)

    def _request_approval(self, ctx: GateContext) -> GateResult:
        """RED 工具的 fallback 审批。真正 MCP elicitation 由 proxy/upstream.py 处理。
        TODO: 签发 approval_token（trace_id + tool_name + args_hash + expiry）留待 upstream.py。
        """
        fallback = self.opt("elicitation_fallback", "stdout")

        if fallback == "deny":
            return GateResult(
                gate_name=self.name,
                decision=Decision.DENY,
                risks=[f"red_tool_denied: {ctx.tool_name}"],
                metadata={"risk_level": RiskLevel.RED.value},
            )

        if fallback == "async_notify":
            return GateResult(
                gate_name=self.name,
                decision=Decision.WARN,
                risks=[f"red_tool_async_notify: {ctx.tool_name}"],
                metadata={
                    "risk_level": RiskLevel.RED.value,
                    "notify_async": True,
                },
            )

        # default: stdout — print approval request to stderr, return REQUIRE_APPROVAL
        print(
            f"[XA-Guard Gate2] APPROVAL REQUIRED\n"
            f"  tool:      {ctx.tool_name}\n"
            f"  arguments: {ctx.arguments}\n"
            f"  trace_id:  {ctx.trace_id}\n"
            f"  user_role: {ctx.user_role}\n"
            f"  (MCP elicitation not available — stdout fallback)",
            file=sys.stderr,
        )
        return GateResult(
            gate_name=self.name,
            decision=Decision.REQUIRE_APPROVAL,
            risks=[f"red_tool_requires_approval: {ctx.tool_name}"],
            metadata={"risk_level": RiskLevel.RED.value},
        )

    def evaluate(self, ctx: GateContext, stage: GateStage = GateStage.INBOUND) -> GateResult:
        risks = self._load_risks()
        risk_level = risks.get(ctx.tool_name, RiskLevel.GREEN)

        if risk_level == RiskLevel.GREEN:
            return GateResult(
                gate_name=self.name,
                decision=Decision.ALLOW,
                metadata={"risk_level": RiskLevel.GREEN.value},
            )

        if risk_level == RiskLevel.YELLOW:
            return GateResult(
                gate_name=self.name,
                decision=Decision.WARN,
                risks=[f"yellow_tool: {ctx.tool_name}"],
                metadata={
                    "risk_level": RiskLevel.YELLOW.value,
                    "notify_async": True,
                },
            )

        # RED
        return self._request_approval(ctx)
