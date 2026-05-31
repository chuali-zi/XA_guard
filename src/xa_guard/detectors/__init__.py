"""XA-Guard 输入检测框架（关卡 1 用）。

★ 设计目标：Gate1 不再写死规则，而是编排一组可插拔的 **Detector**。
   - RuleDetector：YAML 关键词/正则模式（demo 即可用，无依赖）。
   - ModelDetector：调用一个通用 **ModelBackend** 壳子；真实模型（Qwen3Guard /
     ShieldLM / PromptGuard / Llama Guard / 自研微调模型）都实现同一 ModelBackend
     接口，Gate1 不感知具体模型。

所有检测器产出统一的 DetectionResult（一组 DetectionLabel），由 fusion 融合成
最终 Decision。模型与 YAML 混合使用：先 Spotlighting 预处理 → 各检测器并行打标 →
融合判决。

契约稳定性：本包的 base.py 是子 agent 之间的统一契约，等同 types.py 的地位。
任何字段改动需在根目录 log.md 留痕；能力边界变化时同步更新 status.md。
"""
from __future__ import annotations

from xa_guard.detectors.base import (
    DetectionInput,
    DetectionLabel,
    DetectionResult,
    Detector,
    ModelBackend,
)

__all__ = [
    "DetectionInput",
    "DetectionLabel",
    "DetectionResult",
    "Detector",
    "ModelBackend",
]
