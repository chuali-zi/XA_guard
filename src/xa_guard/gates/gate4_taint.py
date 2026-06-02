"""关卡 4 · 机密文件袋（三色信息流污点） — 赛题方向 2 创新点。

子 agent 实施职责：
- 维护 ctx.taint：根据输入来源（InputSource）+ 工具参数中的敏感词初始化
- 加载 ToolCapability 元数据（policies/tool_capabilities.yaml）
- INBOUND：检查 ctx.taint 是否能流到 tool.input_max_taint
- OUTBOUND：根据 tool.output_taint 升级 ctx.taint；阻止机密回流公网
- 标签传播规则：取最严格（PUBLIC < INTERNAL < CONFIDENTIAL）

接口契约：
- 输入：GateContext + tool_capabilities.yaml 路径
- 输出：GateResult.decision ∈ {ALLOW, DENY}（不会 REQUIRE_APPROVAL）
- 副作用：metadata.input_taint, metadata.output_taint, metadata.tool_capability
- 关键：进出向各跑一次（supported_stages=(INBOUND, OUTBOUND)）
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from xa_guard.gates.base import Gate, GateStage
from xa_guard.types import (
    Decision,
    GateContext,
    GateResult,
    InputSource,
    RiskLevel,
    TaintLabel,
    ToolCapability,
)

# 敏感关键字正则（命中任意一个 → CONFIDENTIAL）
_SENSITIVE_PATTERNS = re.compile(
    r"密码|密钥|手机号|银行卡|医疗健康|金融账户|行踪轨迹|敏感个人信息|"
    r"access[_\-]key|secret[_\-]key|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9_]{36}|身份证",
    re.IGNORECASE,
)

# InputSource → 最低推断污点
_SOURCE_TAINT: dict[InputSource, TaintLabel] = {
    InputSource.USER: TaintLabel.PUBLIC,
    InputSource.WEB: TaintLabel.PUBLIC,
    InputSource.DOCUMENT: TaintLabel.INTERNAL,
    InputSource.RAG: TaintLabel.INTERNAL,
    InputSource.MEMORY: TaintLabel.INTERNAL,
    InputSource.TOOL_RESULT: None,  # 保留 ctx.taint，特殊处理
}


def _load_capabilities(path: str | Path) -> dict[str, ToolCapability]:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    caps: dict[str, ToolCapability] = {}
    for item in raw.get("tools", []):
        name = item["tool_name"]
        caps[name] = ToolCapability(
            tool_name=name,
            capabilities=list(item.get("capabilities", [])),
            input_max_taint=TaintLabel(item.get("input_max_taint", "CONFIDENTIAL")),
            output_taint=TaintLabel(item.get("output_taint", "PUBLIC")),
            risk_level=RiskLevel(item.get("risk_level", "green")),
            description=item.get("description", ""),
        )
    return caps


def _scan_sensitive(value: Any) -> bool:
    if isinstance(value, str):
        return bool(_SENSITIVE_PATTERNS.search(value))
    if isinstance(value, dict):
        return any(_scan_sensitive(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(_scan_sensitive(v) for v in value)
    return False


def _cap_to_dict(cap: ToolCapability) -> dict[str, Any]:
    return {
        "tool_name": cap.tool_name,
        "capabilities": cap.capabilities,
        "input_max_taint": cap.input_max_taint.value,
        "output_taint": cap.output_taint.value,
        "risk_level": cap.risk_level.value,
    }


class Gate4Taint(Gate):
    name = "gate4_taint"
    supported_stages = (GateStage.INBOUND, GateStage.OUTBOUND)

    def __init__(self, cfg=None) -> None:
        super().__init__(cfg)
        cap_file = self.opt("tool_capabilities_file", "policies/tool_capabilities.yaml")
        try:
            self.capabilities: dict[str, ToolCapability] = _load_capabilities(cap_file)
        except FileNotFoundError:
            self.capabilities = {}

    def _default_cap(self, tool_name: str) -> ToolCapability:
        return ToolCapability(
            tool_name=tool_name,
            capabilities=[],
            input_max_taint=TaintLabel.CONFIDENTIAL,
            output_taint=TaintLabel.PUBLIC,
        )

    def _infer_taint(self, ctx: GateContext) -> TaintLabel:
        taint = ctx.taint
        for src in ctx.input_sources:
            mapped = _SOURCE_TAINT.get(src)
            if mapped is None:
                # TOOL_RESULT: keep ctx.taint — already in taint
                continue
            taint = taint.merge(mapped)

        # 扫描 arguments 值
        if _scan_sensitive(ctx.arguments):
            taint = taint.merge(TaintLabel.CONFIDENTIAL)

        # 扫描 session_history 中每条消息的 content
        for msg in ctx.session_history:
            content = msg.get("content", "")
            if _scan_sensitive(content):
                taint = taint.merge(TaintLabel.CONFIDENTIAL)
                break

        return taint

    def evaluate(self, ctx: GateContext, stage: GateStage = GateStage.INBOUND) -> GateResult:
        strict = bool(self.opt("strict_mode", False))
        cap = self.capabilities.get(ctx.tool_name) or self._default_cap(ctx.tool_name)

        if stage == GateStage.INBOUND:
            inferred = self._infer_taint(ctx)

            if inferred.can_flow_to(cap.input_max_taint):
                decision = Decision.ALLOW
                risks: list[str] = []
            else:
                decision = Decision.DENY
                risks = [
                    f"taint {inferred.value} > tool input_max {cap.input_max_taint.value}"
                ]

            return GateResult(
                gate_name=self.name,
                decision=decision,
                risks=risks,
                metadata={
                    "taint": inferred.value,
                    "tool_capability": _cap_to_dict(cap),
                },
            )

        # OUTBOUND
        new_taint = ctx.taint.merge(cap.output_taint)
        risks_out: list[str] = []
        out_decision = Decision.ALLOW

        has_external = any(
            c in cap.capabilities for c in ("NETWORK_EXTERNAL", "NOTIFY")
        )
        if has_external and new_taint == TaintLabel.CONFIDENTIAL:
            out_decision = Decision.DENY if not strict else Decision.DENY
            risks_out = [
                f"CONFIDENTIAL data must not flow through {cap.capabilities} tool"
            ]

        if strict and out_decision == Decision.WARN:
            out_decision = Decision.DENY

        return GateResult(
            gate_name=self.name,
            decision=out_decision,
            risks=risks_out,
            metadata={
                "output_taint": new_taint.value,
                "tool_capability": _cap_to_dict(cap),
            },
        )
