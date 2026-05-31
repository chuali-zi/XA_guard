"""融合引擎 —— 把多个 Detector 的 DetectionResult 合并为一个最终 Decision。

融合规则（产品架构 §3.3 关卡 1 语义）：
  1. DENY 胜出：任一 detector 命中 deny 类目 → ALLOW/WARN/DENY 先看 deny。
     但降级规则：RAG 来源的 indirect_injection / assistant 的 pii_leak → 仅 WARN。
  2. 无 DENY 但有 WARN 触发条件 → WARN（非信任来源 / 有命中但非 deny 类目 / 有模型标签）。
  3. 其他情况 → ALLOW。

  4. ★ fail-open：available=False 的检测器完全忽略——"没来投票的人不改变判决"。
     这保证了模型未就绪时 pipeline 不以"信息不足"为由误拦截或误放行。

  DetectionLabel 的 category 分组：

    Deny categories (来自 dangerous_patterns.yaml):
      shell_dangerous, jailbreak_zh, jailbreak_en, system_leak,
      privacy_leak, pii_leak, sql_injection, indirect_injection

    降级规则详情：
      - indirect_injection + RAG来源 → WARN (非 DENY)
      - pii_leak + assistant角色 → WARN (非 DENY)
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from xa_guard.detectors.base import DetectionLabel, DetectionResult
from xa_guard.types import Decision, InputSource

if TYPE_CHECKING:
    from xa_guard.types import GateContext

# 命中即 DENY 的类目（默认，允许配置覆盖）
DEFAULT_DENY_CATEGORIES = frozenset({
    "shell_dangerous",
    "jailbreak_zh",
    "jailbreak_en",
    "system_leak",
    "privacy_leak",
    "pii_leak",
    "sql_injection",
    "indirect_injection",
})

_DENY_DOWNGRADE_RAG: frozenset[str] = frozenset({"indirect_injection"})
_DENY_DOWNGRADE_ASSISTANT: frozenset[str] = frozenset({"pii_leak"})


def _collect_labels(results: list[DetectionResult]) -> list[DetectionLabel]:
    """收集所有可用检测器的 label，并打平为单一列表。"""
    labels: list[DetectionLabel] = []
    for r in results:
        if not r.available:
            continue  # fail-open：不可用的检测器不投票
        labels.extend(r.labels)
    return labels


def _has_untrusted_sources(metadata: dict[str, Any]) -> bool:
    """从 RuleDetector metadata 判断是否存在非信任来源。"""
    sources: list[str] = metadata.get("sources", [])
    untrusted = {"web", "document", "rag", "tool_result", "memory"}
    return bool(set(sources) & untrusted)


def _label_matches_deny(
    label: DetectionLabel,
    deny_categories: frozenset[str],
    input_sources: list[str],
) -> bool:
    """判断单条 label 是否触发 DENY（考虑降级规则）。"""
    cat = label.category
    origin = label.origin or ""

    # 1. 检查元数据降级标记（RuleDetector 产出时已标记）
    downgraded = label.meta.get("downgraded_rag") or label.meta.get("downgraded_assistant")
    if downgraded:
        return False

    # 2. 运行期降级检查（防御性，即便 meta 没标）
    if cat in _DENY_DOWNGRADE_RAG and any(s in {"rag"} for s in input_sources):
        return False
    if cat in _DENY_DOWNGRADE_ASSISTANT and origin == "assistant":
        return False

    return cat in deny_categories


def fuse(
    results: list[DetectionResult],
    ctx: "GateContext | None" = None,
    deny_categories: frozenset[str] = DEFAULT_DENY_CATEGORIES,
) -> tuple[Decision, list[str], dict[str, Any]]:
    """核心融合函数。

    入参：
      results        : 所有检测器的 DetectionResult（含 available=False 的，将被忽略）。
      ctx            : GateContext，用于取得 input_sources 做降级判断。
      deny_categories: 可配置的 DENY 类目集合（支持从 YAML policy 覆盖）。

    返回：
      (decision, risks, metadata)
        decision  : 最终 Decision 枚举。
        risks     : 命中的风险描述列表（给 GateResult.risks）。
        metadata  : 融合上下文（检测器数量、命中统计、降级记录等），写入 GateResult.metadata。
    """
    available_count = sum(1 for r in results if r.available)
    all_labels = _collect_labels(results)
    denied: list[str] = []
    warned: list[str] = []

    if ctx is not None:
        input_sources = [s.value for s in ctx.input_sources] if ctx.input_sources else ["user"]
    else:
        input_sources = ["user"]

    # ── 1. 判断 DENY ──
    for lbl in all_labels:
        if _label_matches_deny(lbl, deny_categories, input_sources):
            denied.append(f"{lbl.category}:{lbl.term}" if lbl.term else lbl.category)

    if denied:
        decision = Decision.DENY
        risks = [f"deny: {d}" for d in denied]
        return (
            decision,
            risks,
            {
                "fusion": "deny_by_category",
                "hits": denied,
                "total_labels": len(all_labels),
                "detectors_available": available_count,
                "detectors_total": len(results),
                "downgrade_applied": any(
                    lbl.meta.get("downgraded_rag") or lbl.meta.get("downgraded_assistant")
                    for lbl in all_labels
                ),
            },
        )

    # ── 2. 判断 WARN ──
    # 触发条件：有命中但非 deny 类目 / 非信任来源 / 模型给了低分标签
    if all_labels:
        warned.extend(f"{lbl.category}:{lbl.term}" if lbl.term else lbl.category for lbl in all_labels)

    if ctx and _has_untrusted_sources(
        next((r.metadata for r in results if r.available and r.detector_name == "rule"), {})
    ):
        if not warned:
            warned.append(f"untrusted_source: {input_sources}")

    if warned:
        decision = Decision.WARN
        risks = [f"warn: {w}" for w in warned]
        return (
            decision,
            risks,
            {
                "fusion": "warn",
                "hits": warned,
                "total_labels": len(all_labels),
                "detectors_available": available_count,
                "detectors_total": len(results),
            },
        )

    # ── 3. ALLOW ──
    return (
        Decision.ALLOW,
        [],
        {
            "fusion": "allow",
            "total_labels": 0,
            "detectors_available": available_count,
            "detectors_total": len(results),
        },
    )
