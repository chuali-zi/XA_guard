"""StubBackend —— 测试用桩后端，不依赖任何真实模型。

用途：
- 默认 is_ready()=False，确保 ModelDetector fail-open 跳过，不阻塞 pipeline。
- 支持 options['ready']=True + options['keyword_labels'] 配置，用于单测验证模型路径真正被走到。
"""
from __future__ import annotations

from typing import Any, Sequence

from xa_guard.detectors.base import DetectionLabel, ModelBackend


class StubBackend(ModelBackend):
    """桩后端：无依赖、零开销，专为测试 pipeline 连通性设计。

    options 字段：
        ready          : bool, default False —— 控制 is_ready() 返回值。
                         False 时 ModelDetector 会 fail-open 跳过（保护现有行为不被破坏）。
        keyword_labels : dict[str, str] —— 关键词 -> category 映射，子串匹配。
                         只在 ready=True 时生效。
        default_score  : float, default 0.9 —— 命中时的 score。
    """

    name: str = "stub"

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        super().__init__(options)
        # _loaded 仅跟踪 load() 是否被调用过（no-op，但语义上"已加载"）
        self._loaded: bool = False

    def load(self) -> None:
        """no-op：stub 不需要加载任何权重，调用后标记 _loaded=True。"""
        self._loaded = True

    def is_ready(self) -> bool:
        # 默认 False —— 保证未配置 ready=True 时 ModelDetector 始终 fail-open 跳过
        return bool(self.options.get("ready", False))

    def classify(
        self,
        texts: Sequence[str],
        categories: Sequence[str] | None = None,
    ) -> list[list[DetectionLabel]]:
        """简单子串匹配，永不抛异常。

        当 ready=False 时返回全空结果（调用方通常不会到达这里，因为 ModelDetector
        在 not is_ready() 时不调用 classify，但为健壮性仍保留此路径）。
        """
        keyword_labels: dict[str, str] = self.options.get("keyword_labels", {})
        default_score: float = float(self.options.get("default_score", 0.9))

        results: list[list[DetectionLabel]] = []
        for text in texts:
            labels: list[DetectionLabel] = []
            # 只在 ready=True 且有 keyword_labels 时做匹配
            if self.is_ready() and keyword_labels:
                text_lower = text.lower()
                for keyword, category in keyword_labels.items():
                    if keyword.lower() in text_lower:
                        # 过滤：若调用方指定 categories 白名单，只保留在列表内的
                        if categories is None or category in categories:
                            labels.append(
                                DetectionLabel(
                                    category=category,
                                    score=default_score,
                                    detector=self.name,
                                    term=keyword,
                                    # origin 留空，由 ModelDetector 补填 inp.origin
                                    origin="",
                                    meta={"matched_text": text},
                                )
                            )
            results.append(labels)
        return results

    def unload(self) -> None:
        self._loaded = False
