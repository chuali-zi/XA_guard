"""关卡 1 · 门口安检（输入攻击识别） — 赛题方向 1。

子 agent 实施职责：
- 输入侧检测：提示注入 / 越狱诱导 / 知识投毒 / 间接指令污染
- 多源输入标签：用户/网页/文档/RAG/记忆/工具结果
- demo 阶段：规则版（关键词 + 模式 + InputSource 风险加权）
- 生产阶段：PromptGuard 2 中文微调 + Llama Guard 3（M2）

接口契约：
- 输入：GateContext（含 tool_name, arguments, input_sources, session_history）
- 输出：GateResult.decision ∈ {ALLOW, WARN, DENY}
- 副作用：在 metadata 写入 detected_patterns / source_risk_score
- 初始化 taint：根据 InputSource 升级 ctx.taint 的最低底线（不在此处直接 mutate ctx）

依赖：xa_guard.types, xa_guard.gates.base
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from xa_guard.gates.base import Gate, GateStage
from xa_guard.types import Decision, GateContext, GateResult, InputSource

_DENY_CATEGORIES = frozenset({
    "shell_dangerous",
    "jailbreak_zh",
    "jailbreak_en",
    "system_leak",
    "indirect_injection",
    "pii_leak",
    "sql_injection",
})

_WARN_SOURCES = frozenset({
    InputSource.WEB,
    InputSource.DOCUMENT,
    InputSource.RAG,
    InputSource.MEMORY,
})

_DEFAULT_SOURCE_WEIGHTS: dict[str, float] = {
    "user": 1.0,
    "web": 1.5,
    "document": 1.5,
    "rag": 1.2,
    "memory": 1.1,
    "tool_result": 1.3,
}


def _load_patterns(patterns_file: str) -> dict[str, list[str]]:
    path = Path(patterns_file)
    if not path.is_absolute():
        # resolve relative to project root (two levels up from this file: gates -> xa_guard -> src -> project)
        project_root = Path(__file__).parent.parent.parent.parent
        path = project_root / patterns_file
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return raw.get("patterns", {})


def _build_text(ctx: GateContext) -> str:
    parts: list[str] = []
    if ctx.tool_name:
        parts.append(ctx.tool_name)
    if ctx.arguments:
        parts.append(json.dumps(ctx.arguments, ensure_ascii=False))
    for entry in ctx.session_history:
        if isinstance(entry, dict):
            content = entry.get("content", "")
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        parts.append(str(block.get("text", "")))
    return "\n".join(parts).lower()


def _scan_patterns(
    text: str, patterns: dict[str, list[str]]
) -> list[tuple[str, str]]:
    hits: list[tuple[str, str]] = []
    for category, terms in patterns.items():
        for term in terms:
            if term.lower() in text:
                hits.append((category, term))
    return hits


def _compute_source_risk(
    sources: list[InputSource], weights: dict[str, float]
) -> float:
    if not sources:
        return weights.get("user", 1.0)
    total = sum(weights.get(src.value, 1.0) for src in sources)
    return round(total / len(sources), 4)


class Gate1Input(Gate):
    name = "gate1_input"
    supported_stages = (GateStage.INBOUND,)

    def evaluate(self, ctx: GateContext, stage: GateStage = GateStage.INBOUND) -> GateResult:
        patterns_file: str = self.opt("patterns_file", "policies/dangerous_patterns.yaml")
        source_weights: dict[str, float] = self.opt(
            "source_risk_weights", _DEFAULT_SOURCE_WEIGHTS
        )

        patterns = _load_patterns(patterns_file)
        text = _build_text(ctx)
        hits = _scan_patterns(text, patterns)

        source_risk_score = _compute_source_risk(ctx.input_sources, source_weights)

        detected: list[str] = [f"{cat}:{term}" for cat, term in hits]
        risks: list[str] = [f"pattern_match: {cat}:{term}" for cat, term in hits]

        metadata: dict[str, Any] = {
            "detected_patterns": detected,
            "source_risk_score": source_risk_score,
        }

        deny_hit = any(cat in _DENY_CATEGORIES for cat, _ in hits)
        warn_source = any(src in _WARN_SOURCES for src in ctx.input_sources)

        if deny_hit:
            decision = Decision.DENY
        elif hits or warn_source:
            decision = Decision.WARN
            if not risks and warn_source:
                risks.append(f"untrusted_source: {[s.value for s in ctx.input_sources if s in _WARN_SOURCES]}")
        else:
            decision = Decision.ALLOW

        return GateResult(
            gate_name=self.name,
            decision=decision,
            risks=risks,
            metadata=metadata,
        )
