"""ModelDetector —— 将任意 ModelBackend 包装为 Detector 接口。

设计要点：
- fail-open：后端未就绪或推理异常时返回 available=False，不阻塞 pipeline。
  其余检测器的票仍有效；fusion 忽略 available=False 的投票，不因此误杀请求。
- 惰性加载：detect() 首次调用时若 backend 未 ready，先尝试 load()；
  仍未 ready 则 fail-open，保证 pipeline 在无模型环境下正常启动。
- category_map：把后端原生类目名归一到项目统一类目命名空间，消除各模型差异。
- timeout_ms：目前仅存字段 + 记录到 metadata，真实超时控制需按后端（子进程/grpc）
  实现，同步推理不适合用 signal/thread，留 TODO。
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from xa_guard.detectors.base import (
    DetectionInput,
    DetectionLabel,
    DetectionResult,
    Detector,
    ModelBackend,
)

if TYPE_CHECKING:
    from xa_guard.types import GateContext


class ModelDetector(Detector):
    """将 ModelBackend 包装为统一 Detector 接口。

    参数：
        backend      : 任意 ModelBackend 实现。
        categories   : 传给 backend.classify() 的类目白名单（None=全部）。
        threshold    : score 低于此值的 label 被过滤掉，默认 0.5。
        timeout_ms   : 推理超时（毫秒），TODO：真实实现依赖后端类型，暂记录到 metadata。
        fail_open    : True=异常时 available=False 放行；False=仍不抛但在 metadata 标注 error。
                       两种情况都不向上抛异常（契约要求）。
        category_map : 把后端原生类目名映射到项目统一类目名；映射不到的保留原名。
    """

    def __init__(
        self,
        backend: ModelBackend,
        categories: list[str] | None = None,
        threshold: float = 0.5,
        timeout_ms: int | None = None,
        fail_open: bool = True,
        category_map: dict[str, str] | None = None,
    ) -> None:
        self.backend = backend
        self.categories = categories
        self.threshold = threshold
        self.timeout_ms = timeout_ms  # TODO: 真实超时控制留待后续按后端类型（子进程/gRPC）实现
        self.fail_open = fail_open
        # 归一映射表：后端原生类目 -> 项目统一类目
        self.category_map: dict[str, str] = category_map or {}

    @property
    def name(self) -> str:  # type: ignore[override]
        return f"model:{self.backend.name}"

    def warmup(self) -> None:
        """提前触发 backend.load()，供 pipeline 启动时预热（捕获异常，失败不抛）。"""
        try:
            self.backend.load()
        except Exception:
            # warmup 失败不影响启动；detect() 首次调用时会再次尝试 load
            pass

    def _map_category(self, category: str) -> str:
        """按 category_map 归一类目名；映射不到时保留原名。"""
        return self.category_map.get(category, category)

    def _make_unavailable(self, reason: str, latency_ms: float = 0.0, extra: dict[str, Any] | None = None) -> DetectionResult:
        meta: dict[str, Any] = {"reason": reason}
        if self.timeout_ms is not None:
            meta["timeout_ms_config"] = self.timeout_ms
        if extra:
            meta.update(extra)
        return DetectionResult(
            labels=[],
            detector_name=self.name,
            available=False,
            latency_ms=latency_ms,
            metadata=meta,
        )

    def detect(
        self,
        inp: DetectionInput,
        ctx: "GateContext | None" = None,
    ) -> DetectionResult:
        """对输入打标，返回 DetectionResult。绝不向上抛异常。"""
        t0 = time.perf_counter()

        try:
            # ── 1. 惰性加载：backend 未就绪时先尝试 load ──────────────────────
            if not self.backend.is_ready():
                try:
                    self.backend.load()
                except Exception as load_err:
                    # load 失败 → fail-open，标记原因
                    latency_ms = (time.perf_counter() - t0) * 1000
                    return self._make_unavailable(
                        "model_load_failed",
                        latency_ms,
                        {"load_error": str(load_err)},
                    )

            # load 完还不 ready（stub ready=False 场景）→ fail-open
            if not self.backend.is_ready():
                latency_ms = (time.perf_counter() - t0) * 1000
                return self._make_unavailable("model_unavailable", latency_ms)

            # ── 2. 推理：优先用 raw_text（未预处理），回退到 text ──────────────
            text = inp.raw_text or inp.text
            raw_results: list[list[DetectionLabel]] = self.backend.classify(
                [text], self.categories
            )
            # classify 应返回与 texts 等长的列表；取第 0 项
            per_text_labels: list[DetectionLabel] = raw_results[0] if raw_results else []

            # ── 3. 过滤 + 归一化 label ────────────────────────────────────────
            filtered: list[DetectionLabel] = []
            for lbl in per_text_labels:
                # 按 threshold 过滤低置信度标签
                if lbl.score < self.threshold:
                    continue
                # 归一类目名（category_map）
                unified_category = self._map_category(lbl.category)
                # 补填 origin（若 label 自己未填，用 inp.origin）
                resolved_origin = lbl.origin if lbl.origin else inp.origin
                filtered.append(
                    DetectionLabel(
                        category=unified_category,
                        score=lbl.score,
                        detector=lbl.detector or self.backend.name,
                        term=lbl.term,
                        origin=resolved_origin,
                        meta=lbl.meta,
                    )
                )

            latency_ms = (time.perf_counter() - t0) * 1000
            meta: dict[str, Any] = {}
            if self.timeout_ms is not None:
                # 记录超时配置，真实超时控制需后续实现
                meta["timeout_ms_config"] = self.timeout_ms

            return DetectionResult(
                labels=filtered,
                detector_name=self.name,
                available=True,
                latency_ms=latency_ms,
                metadata=meta,
            )

        except Exception as exc:
            # ── 任何未预期异常都在此兜底，绝不向上抛 ─────────────────────────
            latency_ms = (time.perf_counter() - t0) * 1000
            error_meta: dict[str, Any] = {"error": str(exc), "error_type": type(exc).__name__}
            if self.timeout_ms is not None:
                error_meta["timeout_ms_config"] = self.timeout_ms
            # fail_open=True 或 False 都不抛；区别在 metadata 中标注以便审计
            if not self.fail_open:
                error_meta["fail_open"] = False
            return DetectionResult(
                labels=[],
                detector_name=self.name,
                available=False,
                latency_ms=latency_ms,
                metadata=error_meta,
            )
