"""关卡 4 · 机密文件袋（三色信息流污点） — 赛题方向 2 创新点。

子 agent 实施职责：
- 维护 ctx.taint：根据输入来源（InputSource）+ 工具参数中的敏感词初始化
- 加载 ToolCapability 元数据（policies/baseline/gate4_capabilities.yaml）
- INBOUND：检查 ctx.taint 是否能流到 tool.input_max_taint
- OUTBOUND：根据 tool.output_taint 升级 ctx.taint；阻止机密回流公网
- 标签传播规则：取最严格（PUBLIC < INTERNAL < CONFIDENTIAL）

接口契约：
- 输入：GateContext + gate4_capabilities.yaml 路径
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
from xa_guard.policy.layered import get_global_source
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
# 兜底：未启用 LayeredPolicySource 时直接用此 baseline 正则（与 policies/baseline/gate4_sensitive_patterns.yaml 一致）
_SENSITIVE_PATTERNS = re.compile(
    r"密码|密钥|手机号|银行卡|医疗健康|金融账户|行踪轨迹|敏感个人信息|"
    r"password|passwd|pwd|access[_\-]key|secret[_\-]key|AKIA[0-9A-Z]{16}|"
    r"ghp_[A-Za-z0-9_]{36}|身份证",
    re.IGNORECASE,
)
_HIGH_CONFIDENCE_ROUTING_PATTERNS = re.compile(
    r"密码|密钥|手机号|银行卡|医疗健康|金融账户|行踪轨迹|敏感个人信息|身份证|"
    r"\b[1-9]\d{5}(18|19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[0-9Xx]\b|"
    r"(?<!\d)1[3-9]\d{9}(?!\d)|"
    r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)|"
    r"\b[0-9A-HJ-NPQRTUWXY]{2}\d{6}[0-9A-HJ-NPQRTUWXY]{10}\b|"
    r"\b(?:10(?:\.\d{1,3}){3}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}|"
    r"192\.168(?:\.\d{1,3}){2}|127(?:\.\d{1,3}){3}|169\.254(?:\.\d{1,3}){2})\b|"
    r"password|passwd|\bpwd\b|access[_\-]key|secret[_\-]key|"
    r"\bBearer\s+[A-Za-z0-9._~+\-/]+=*|"
    r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b|"
    r"\b(?:api|access|secret|private|auth|session)[_\- ]?(?:key|token|secret)\b\s*[:=]\s*[\"']?[A-Za-z0-9._~+\-/]{16,}[\"']?|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9_]{36}|"
    r"(?:秘密|机密|绝密)\s*(?:★|\*)?\s*(?:\d+\s*年|长期|永久)?|"
    r"(?:秘密级|机密级|绝密级|国家秘密|工作秘密|商业秘密|商密)|"
    r"(?:内部资料|内部文件|内部使用|内部流转|内部公开|不得外传|严禁外传|禁止外传|涉密|保密)",
    re.IGNORECASE,
)

_ROUTING_VALUE_KEYS = {
    "to",
    "cc",
    "bcc",
    "from",
    "reply_to",
    "recipient",
    "recipients",
    "channel",
}

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


def _scan_sensitive(value: Any, pattern: re.Pattern | None = None) -> bool:
    pat = pattern if pattern is not None else _SENSITIVE_PATTERNS
    if isinstance(value, str):
        return bool(pat.search(value))
    if isinstance(value, dict):
        for k, v in value.items():
            if _scan_sensitive(k, pat):
                return True
            key = str(k).lower().replace("-", "_")
            if key in _ROUTING_VALUE_KEYS:
                if _scan_routing_value_sensitive(v):
                    return True
                continue
            if _scan_sensitive(v, pat):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(_scan_sensitive(v, pat) for v in value)
    return False


def _scan_routing_value_sensitive(value: Any) -> bool:
    if isinstance(value, str):
        return bool(_HIGH_CONFIDENCE_ROUTING_PATTERNS.search(value))
    if isinstance(value, dict):
        return any(
            _scan_sensitive(k) or _scan_routing_value_sensitive(v)
            for k, v in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_scan_routing_value_sensitive(v) for v in value)
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
        cap_file = self.opt("tool_capabilities_file", "policies/baseline/gate4_capabilities.yaml")
        try:
            self.capabilities: dict[str, ToolCapability] = _load_capabilities(cap_file)
        except FileNotFoundError:
            self.capabilities = {}

    def _default_cap(self, tool_name: str) -> ToolCapability:
        # Fail-closed 兜底：未登记工具视为最高风险来源。
        # input_max_taint=PUBLIC：任何非 PUBLIC 数据（INTERNAL/CONFIDENTIAL）流入未知工具均触发 INBOUND DENY，
        # 防止机密数据泄露给未经审查的工具。
        # output_taint=CONFIDENTIAL：假设未知工具的输出可能携带机密，使 OUTBOUND 阶段对其外发严格审查。
        # capabilities=["NETWORK_EXTERNAL"]：假设未知工具可能具有外网访问能力，确保 OUTBOUND 机密外泄检查生效。
        return ToolCapability(
            tool_name=tool_name,
            capabilities=["NETWORK_EXTERNAL"],
            input_max_taint=TaintLabel.PUBLIC,
            output_taint=TaintLabel.CONFIDENTIAL,
        )

    def _current_caps(self) -> dict[str, ToolCapability]:
        """LayeredPolicySource opt-in（cfg.gate4.prefer_layered: true）；默认 legacy。"""
        if bool(self.opt("prefer_layered", False)):
            layered = get_global_source()
            if layered is not None:
                caps = layered.get_tool_capabilities()
                if caps:
                    return caps
        return self.capabilities

    def _current_pattern(self) -> re.Pattern:
        if bool(self.opt("prefer_layered", False)):
            layered = get_global_source()
            if layered is not None:
                pat = layered.get_sensitive_pattern()
                if pat is not None:
                    return pat
        return _SENSITIVE_PATTERNS

    def _infer_taint(self, ctx: GateContext) -> TaintLabel:
        taint = ctx.taint
        for src in ctx.input_sources:
            mapped = _SOURCE_TAINT.get(src)
            if mapped is None:
                # TOOL_RESULT: keep ctx.taint — already in taint
                continue
            taint = taint.merge(mapped)

        pat = self._current_pattern()
        # 扫描 arguments 值
        if _scan_sensitive(ctx.arguments, pat):
            taint = taint.merge(TaintLabel.CONFIDENTIAL)

        # 扫描 session_history 中每条消息的 content
        for msg in ctx.session_history:
            content = msg.get("content", "")
            if _scan_sensitive(content, pat):
                taint = taint.merge(TaintLabel.CONFIDENTIAL)
                break

        return taint

    def evaluate(self, ctx: GateContext, stage: GateStage = GateStage.INBOUND) -> GateResult:
        # strict_mode 保留读取以兼容 configs/xa-guard.yaml 的 strict_mode 配置项，
        # 但 gate4 当前逻辑中 OUTBOUND 机密外泄直接 DENY，无 WARN 路径，故 strict 不影响实际决策。
        # 如未来需要 WARN 升级语义，在此处重新引入逻辑。
        _ = self.opt("strict_mode", False)  # 保留兼容，暂未使用（见上方注释）
        caps = self._current_caps()
        cap = caps.get(ctx.tool_name) or self._default_cap(ctx.tool_name)

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
            # 机密数据通过外网/通知工具外发：直接 DENY（无 WARN 路径，fail-closed）
            out_decision = Decision.DENY
            risks_out = [
                f"CONFIDENTIAL data must not flow through {cap.capabilities} tool"
            ]

        return GateResult(
            gate_name=self.name,
            decision=out_decision,
            risks=risks_out,
            metadata={
                "output_taint": new_taint.value,
                "tool_capability": _cap_to_dict(cap),
            },
        )
