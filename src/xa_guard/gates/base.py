"""Gate 抽象基类。所有关卡子类化此 + 实现 evaluate()。"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from enum import Enum

from xa_guard.config import GateConfig
from xa_guard.types import Decision, GateContext, GateResult


class GateStage(str, Enum):
    """关卡执行阶段。Gate4 / Gate6 需要进出向各跑一次。"""

    INBOUND = "inbound"     # 工具调用前
    OUTBOUND = "outbound"   # 工具返回后


class Gate(ABC):
    """所有关卡的统一接口。

    子类应：
    1. 实现 `evaluate(ctx, stage)` 返回 GateResult。
    2. 默认实现 latency_ms 自动计时。
    3. 不要在 evaluate 中 mutate ctx — 由 pipeline 统一 append。
    """

    name: str = "gate"
    supported_stages: tuple[GateStage, ...] = (GateStage.INBOUND,)

    def __init__(self, cfg: GateConfig | None = None) -> None:
        self.cfg = cfg or GateConfig()

    @property
    def enabled(self) -> bool:
        return self.cfg.enabled

    def opt(self, key: str, default=None):
        return self.cfg.options.get(key, default)

    @abstractmethod
    def evaluate(self, ctx: GateContext, stage: GateStage = GateStage.INBOUND) -> GateResult:
        """实施关卡检查；返回 GateResult。"""

    def __call__(self, ctx: GateContext, stage: GateStage = GateStage.INBOUND) -> GateResult:
        if not self.enabled:
            return GateResult(gate_name=self.name, decision=Decision.ALLOW, note="disabled")
        if stage not in self.supported_stages:
            return GateResult(gate_name=self.name, decision=Decision.ALLOW, note=f"stage {stage} skipped")
        t0 = time.perf_counter()
        try:
            result = self.evaluate(ctx, stage)
        except Exception as exc:  # 关卡内部异常不应崩 pipeline
            return GateResult(
                gate_name=self.name,
                decision=Decision.WARN,
                risks=[f"gate_error: {type(exc).__name__}: {exc}"],
                latency_ms=(time.perf_counter() - t0) * 1000,
            )
        result.latency_ms = (time.perf_counter() - t0) * 1000
        if not result.gate_name:
            result.gate_name = self.name
        return result
