"""关卡 2 · 办事大厅（HITL 审批） — 赛题方向 2。

工具调用风险等级判定：
- risk_level 唯一事实源：policies/baseline/gate4_capabilities.yaml（risk_level 字段）
  由 layered.py 的 _derive_tool_risks_from_caps() 加载时派生；gate2_tool_risks.yaml 已废弃。
- RED: 同步阻塞，走 elicitation fallback（stdout/deny/async_notify）
- YELLOW: 异步通知，Decision.WARN + metadata["notify_async"]=True
- GREEN: Decision.ALLOW
- 未登记工具默认 YELLOW（fail-closed，暴露未知工具，可配置 default_risk 选项覆盖）

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

    def __init__(self, cfg=None) -> None:
        super().__init__(cfg)
        risk_file = self.opt("tool_risk_file", "policies/baseline/gate2_tool_risks.yaml")
        try:
            self._legacy_risks = _load_tool_risks(risk_file)
        except FileNotFoundError:
            self._legacy_risks = {}

    def _load_risks(self) -> dict[str, RiskLevel]:
        """LayeredPolicySource（baseline+overlay 合并）opt-in；默认走单文件。

        prefer_layered: true 时优先 layered（生产推荐），否则保持 legacy（兼容单测）。
        risk_level 唯一事实源：gate4_capabilities.yaml；layered 模式下由
        _derive_tool_risks_from_caps() 自动派生，不依赖 gate2_tool_risks.yaml。
        """
        if bool(self.opt("prefer_layered", False)):
            layered = get_global_source()
            if layered is not None:
                risks = layered.get_tool_risks()
                if risks:
                    return risks
        # legacy 路径：单文件直读（单测兼容；tool_risk_file 配置指向 gate2_tool_risks.yaml 仅作历史保留）
        return self._legacy_risks

    def _request_approval(self, ctx: GateContext) -> GateResult:
        """RED 工具的 fallback 审批。真正 MCP elicitation 由 proxy/upstream.py 处理。

        approval_token 的签发/验签已落在 xa_guard.approval（人工 approve 时由
        upstream.py 签发，pipeline.run_after_approval 执行前验签，gate6 写审计）。
        本关卡只负责出 REQUIRE_APPROVAL 决策，不签发令牌。
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
        # 未登记工具 fail-closed：默认 YELLOW（warn + async_notify），而非 GREEN（静默放行）。
        # 安全网关对未知工具应暴露而不应静默。可通过 opt("default_risk") 覆盖（"green"/"yellow"/"red"）。
        # risk_level 唯一事实源：policies/baseline/gate4_capabilities.yaml。
        _default_risk_str = str(self.opt("default_risk", "yellow")).lower()
        try:
            _default_risk = RiskLevel(_default_risk_str)
        except ValueError:
            _default_risk = RiskLevel.YELLOW
        risk_level = risks.get(ctx.tool_name, _default_risk)

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
