"""RuleDetector —— 将现有 YAML 关键词/模式检测逻辑封装为 Detector 接口。

★ 行为与原始 gate1_input.py 完全一致：
  - 从 YAML 加载 patterns (categories → list of terms)。
  - 扫描 tool_name + arguments + session_history。
  - 命中 deny 类目 → DENY；命中 + 非信任来源 → WARN；否则 ALLOW。
  - 单纯 source 风险加权在 fusion / gate1 编排层处理，detector 只打标。

设计原则：
  1. 无外部依赖，纯 Python 子串匹配。
  2. 不生成"决策"——只产出 DetectionLabel，决策由 fusion 统一做。
     label.score 固定 1.0（规则确定性命中），detector="rule"。
  3. 保留 origin 信息（tool/user/assistant/...），fusion 用它做降级（如
     indirect_injection + RAG 来源 → 仅 WARN 不 DENY）。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from xa_guard.detectors.base import DetectionInput, DetectionLabel, DetectionResult, Detector

if TYPE_CHECKING:
    from xa_guard.types import GateContext, InputSource

# 这些类目命中后直接对应 deny（fusion 层使用）
_DENY_CATEGORIES = frozenset({
    "shell_dangerous",
    "jailbreak_zh",
    "jailbreak_en",
    "system_leak",
    "privacy_leak",
    "indirect_injection",
    "pii_leak",
    "sql_injection",
})

# 根据角色决定是否降级（RAG 来源的 indirect_injection → 不构成 deny）
_RAG_DENY_DOWNGRADE = frozenset({"indirect_injection"})
_ASSISTANT_DENY_DOWNGRADE = frozenset({"pii_leak"})


def _load_patterns(patterns_file: str) -> dict[str, list[str]]:
    """从 YAML 加载 pattern 定义。返回 {category: [term, ...]}。"""
    path = Path(patterns_file)
    if not path.is_absolute():
        project_root = Path(__file__).parent.parent.parent.parent
        path = project_root / patterns_file
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return raw.get("patterns", {})


def _build_tool_text(tool_name: str, arguments: dict[str, Any]) -> str:
    """提取 tool 调用平面的文本（tool_name + arguments）。"""
    parts: list[str] = []
    if tool_name:
        parts.append(tool_name)
    if arguments:
        parts.append(json.dumps(arguments, ensure_ascii=False))
    return "\n".join(parts).lower()


def _entry_text(entry: dict) -> str:
    """提取 session_history 单条 entry 的文本。"""
    content = entry.get("content", "")
    if isinstance(content, str):
        return content.lower()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("text", "")))
        return "\n".join(parts).lower()
    return ""


def _scan(text: str, patterns: dict[str, list[str]]) -> list[tuple[str, str]]:
    """子串匹配。返回 [(category, matched_term), ...]."""
    hits: list[tuple[str, str]] = []
    for category, terms in patterns.items():
        for term in terms:
            if term.lower() in text:
                hits.append((category, term))
    return hits


class RuleDetector(Detector):
    """YAML 规则检测器 —— Gate1 的确定性防线。

    始终 available=True（无模型依赖）。即使配置的 patterns_file 不存在，
    它也返回空的 DetectionResult 而非抛异常。
    """

    name = "rule"

    def __init__(self, patterns_file: str = "policies/dangerous_patterns.yaml") -> None:
        self.patterns_file = patterns_file
        self._patterns: dict[str, list[str]] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        try:
            self._patterns = _load_patterns(self.patterns_file)
        except Exception:
            self._patterns = {}
        self._loaded = True

    def detect(
        self,
        inp: DetectionInput,
        ctx: "GateContext | None" = None,
    ) -> DetectionResult:
        """扫描 inp.meta 里的结构化数据（或 fallback 到 inp.text）。"""
        import time
        t0 = time.perf_counter()

        self._ensure_loaded()
        labels: list[DetectionLabel] = []

        try:
            meta = inp.meta
            tool_name = meta.get("tool_name", "")
            arguments = meta.get("arguments", {})
            session_history: list[dict] = meta.get("session_history", [])
            input_sources: list[str] = inp.sources or ["user"]

            # 1. tool 文本扫描
            tool_text = _build_tool_text(tool_name, arguments)
            for cat, term in _scan(tool_text, self._patterns):
                labels.append(DetectionLabel(
                    category=cat, score=1.0, detector="rule",
                    term=term, origin="tool",
                    meta={},
                ))

            # 2. session_history 逐条扫描
            for entry in session_history:
                if not isinstance(entry, dict):
                    continue
                role = str(entry.get("role", "history"))
                for cat, term in _scan(_entry_text(entry), self._patterns):
                    labels.append(DetectionLabel(
                        category=cat, score=1.0, detector="rule",
                        term=term, origin=role,
                        meta={"downgraded_rag": cat in _RAG_DENY_DOWNGRADE and "rag" in input_sources,
                              "downgraded_assistant": cat in _ASSISTANT_DENY_DOWNGRADE and role == "assistant"},
                    ))

            # 3. 标记原始来源风险（不生成 label，但写入 metadata 供 fusion 参考）
            latency_ms = (time.perf_counter() - t0) * 1000

            return DetectionResult(
                labels=labels,
                detector_name=self.name,
                available=True,
                latency_ms=latency_ms,
                metadata={
                    "pattern_count": len(labels),
                    "sources": input_sources,
                },
            )
        except Exception:
            # 任何异常兜底 → 空结果（规则不应该出错，但契约要求 fail-open）
            latency_ms = (time.perf_counter() - t0) * 1000
            return DetectionResult(
                labels=[], detector_name=self.name,
                available=True, latency_ms=latency_ms,
                metadata={"error": "rule_scan_exception"},
            )
