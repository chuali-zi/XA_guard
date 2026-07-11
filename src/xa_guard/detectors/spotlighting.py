"""Spotlighting 预处理 —— 对非用户来源的文本片段加标记。

基于 Microsoft Spotlighting 论文思路：用特殊包裹标记非信任来源的输入内容，
让下游模型/规则能识别"这段文本不是用户直接写的"，从而对间接注入保持警觉。

在 Gate1 里，Spotlighting 是 **预处理步骤**（在 feed 给检测器之前）：
  1. 遍历 GateContext 的 input_sources → 判断哪些来源需要标记。
  2. 对需要标记的来源，在 DetectionInput.raw_text 中包裹标记。
  3. 标记后的文本存入 DetectionInput.meta["spotlighted"] 供审计。

默认标记策略：
  - USER → 不标记（信任用户直接输入）。
  - WEB / DOCUMENT / RAG / TOOL_RESULT / MEMORY → 标记。
  使用 `<untrusted_source type="web">...</untrusted_source>` 格式。
  标记仅加在非用户来源的 session_history 片段上。

这符合 status.md 的务实路径：规则层 + Spotlighting + Qwen3Guard → 三层防御。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from xa_guard.detectors.base import DetectionInput

if TYPE_CHECKING:
    from xa_guard.types import GateContext

# 需要标记的来源（信任度低于 user 的）
_UNTRUSTED_SOURCES = frozenset({"web", "document", "rag", "tool_result", "memory"})


def _source_needs_spotlight(source: str) -> bool:
    return source in _UNTRUSTED_SOURCES


def apply_spotlighting(inp: DetectionInput, ctx: "GateContext | None" = None) -> DetectionInput:
    """对 DetectionInput 的 raw_text 加 Spotlighting 包裹标记。

    实现：对 session_history 中非 user 来源的片段包标记。
    标记格式：`<untrusted_source type="SOURCE">...text...</untrusted_source>`

    spotlighted 文本存入 inp.meta["spotlighted_text"]（供审计追踪），
    inp.raw_text 被替换为标记版本；后续检测器用 raw_text 即可感知来源。

    若 ctx 为 None，不做任何处理，直接返回原 inp。
    """
    if ctx is None:
        return inp

    sources = ctx.input_sources if ctx.input_sources else []
    session_history: list[dict] = ctx.session_history if ctx.session_history else []

    # 如果全部来源都是 user，不需要标记
    if all(s.value == "user" for s in sources) and not session_history:
        return inp

    parts: list[str] = []

    # 工具调用平面（tool_name + arguments）—— 总是来自 action 平面，加标注
    if ctx.tool_name:
        parts.append(f"[TOOL_CALL] {ctx.tool_name}")

    # 处理 session_history：非 user/assistant 来源的内容包裹标记
    for entry in session_history:
        if not isinstance(entry, dict):
            continue
        role = str(entry.get("role", ""))
        content = entry.get("content", "")
        content_str: str = ""
        if isinstance(content, str):
            content_str = content
        elif isinstance(content, list):
            content_str = "\n".join(str(block.get("text", "")) for block in content if isinstance(block, dict))

        if not content_str.strip():
            continue

        # tool 角色且存在非 user 的来源 → 标记
        needs_spotlight = role == "tool" and any(_source_needs_spotlight(s.value) for s in sources)
        if needs_spotlight:
            # 取第一个不信任的 source 类型名作为标记类型
            untrusted = [s.value for s in sources if _source_needs_spotlight(s.value)]
            src_label = untrusted[0] if untrusted else "unknown"
            parts.append(f'<untrusted_source type="{src_label}">{content_str}</untrusted_source>')
        else:
            parts.append(f"[{role}] {content_str}")

    spotlighted = "\n".join(parts) if parts else inp.raw_text

    # 更新 meta 记录
    meta = dict(inp.meta)
    meta["spotlighted"] = True
    meta["spotlighted_text"] = spotlighted
    meta["untrusted_sources"] = [s.value for s in sources if _source_needs_spotlight(s.value)]

    return DetectionInput(
        text=inp.text,
        raw_text=spotlighted,               # ← 关键：raw_text 替换为标记版
        source=inp.source,
        origin=inp.origin,
        sources=inp.sources,
        meta=meta,
    )
