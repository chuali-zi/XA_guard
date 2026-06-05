"""关卡 1 · 门口安检（输入攻击识别） — 赛题方向 1。

★ v2 · 模型+YAML 混合架构（2026-05-28 重构）

  Gate1 不再写死规则逻辑，而是编排一组可插拔的 Detector：
    - RuleDetector     → YAML 关键词子串匹配（现有规则，零依赖，始终可用）
    - ModelDetector(s) → 通用 ModelBackend 壳子（stub 默认 fail-open；后续接入
                          Qwen3Guard / ShieldLM / PromptGuard 等零改动 Gate1）

  处理流程：
    1. GateContext → DetectionInput（归一化）
    2. Spotlighting 预处理（非 user 来源加 <untrusted_source> 标记）
    3. 并行运行所有 detector（rule + 配置的模型探测器）→ DetectionResult[]
    4. Fusion 融合 → 最终 Decision（ALLOW/WARN/DENY）
    5. 返回 GateResult（向后兼容 pipeline）

  ★ 向后兼容：现有单元测试无需改动。默认配置 id="rule-only" 路径等价于旧版规则检测。
    模型路径通过 config.options["detectors"] 启用；不配则只跑 RuleDetector。

  依赖：xa_guard.detectors.*, xa_guard.types, xa_guard.gates.base
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from xa_guard.detectors.base import DetectionInput, Detector
from xa_guard.detectors.fusion import DEFAULT_DENY_CATEGORIES, fuse
from xa_guard.detectors.rule_detector import RuleDetector
from xa_guard.detectors.spotlighting import apply_spotlighting
from xa_guard.gates.base import Gate, GateStage
from xa_guard.types import Decision, GateContext, GateResult, InputSource

# ── 旧版兼容常量（类别分组、来源权重） ──────────────────────────────────
_DENY_CATEGORIES = frozenset({
    "shell_dangerous", "jailbreak_zh", "jailbreak_en",
    "system_leak", "privacy_leak", "indirect_injection",
    "pii_leak", "sql_injection",
})

_WARN_SOURCES = frozenset({
    InputSource.WEB, InputSource.DOCUMENT,
    InputSource.RAG, InputSource.MEMORY,
})

_DEFAULT_SOURCE_WEIGHTS: dict[str, float] = {
    "user": 1.0, "web": 1.5, "document": 1.5,
    "rag": 1.2, "memory": 1.1, "tool_result": 1.3,
}


def _compute_source_risk(
    sources: list[InputSource], weights: dict[str, float] | None = None
) -> float:
    if weights is None:
        weights = _DEFAULT_SOURCE_WEIGHTS
    if not sources:
        return weights.get("user", 1.0)
    total = sum(weights.get(s.value, 1.0) for s in sources)
    return round(total / len(sources), 4)


def _load_category_map(path_value: str | None) -> dict[str, str]:
    """Load a model native-category mapping from YAML.

    Accepts either ``{category_map: {...}}`` or a flat mapping. Missing or
    malformed files return an empty map so model startup remains fail-open.
    """
    if not path_value:
        return {}
    try:
        path = Path(path_value)
        if not path.is_absolute():
            project_root = Path(__file__).parent.parent.parent.parent
            path = project_root / path_value
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        mapping = raw.get("category_map", raw) if isinstance(raw, dict) else {}
        return {str(k): str(v) for k, v in mapping.items()}
    except Exception:
        return {}


@dataclass
class DetectorSpec:
    """配置里的一条 detector 声明（从 GateConfig options.detectors 解析）。"""
    name: str = ""
    type: str = "rule"          # "rule" | "model"
    enabled: bool = True
    options: dict[str, Any] = field(default_factory=dict)


# ──────────────────────────────────────────────────────────────────────
# Gate1Input - 检测器编排器
# ──────────────────────────────────────────────────────────────────────

class Gate1Input(Gate):
    name = "gate1_input"
    supported_stages = (GateStage.INBOUND,)

    def __init__(self, cfg=None) -> None:
        super().__init__(cfg)
        # 从 cfg.options 解析探测器配置
        raw_detectors: list[dict[str, Any]] = self.opt("detectors", [])
        self.spotlight_enabled: bool = self.opt("spotlighting", {}).get("enabled", False)
        self.source_weights: dict[str, float] = self.opt(
            "source_risk_weights", _DEFAULT_SOURCE_WEIGHTS
        )
        self.deny_categories: frozenset[str] = frozenset(
            self.opt("deny_categories", list(DEFAULT_DENY_CATEGORIES))
        )

        # —— 解析 detector spec ——
        specs: list[DetectorSpec] = []
        if raw_detectors:
            for spec in raw_detectors:
                specs.append(DetectorSpec(
                    name=spec.get("name", ""),
                    type=spec.get("type", "rule"),
                    enabled=spec.get("enabled", True),
                    options={k: v for k, v in spec.items() if k not in ("name", "type", "enabled")},
                ))
        # 默认：至少有一个 rule 检测器
        if not specs:
            pat_file: str = self.opt("patterns_file", "policies/baseline/gate1_input_patterns.yaml")
            specs.append(DetectorSpec(
                name="rule",
                type="rule",
                enabled=True,
                options={"patterns_file": pat_file},
            ))

        self._specs = specs
        self._detectors: list[Detector] = []
        self._built = False

    # ─── 探测器工厂 ──────────────────────────────────────────────────

    def _build_detectors(self) -> list[Detector]:
        """按配置实例化所有探测器（惰性、一次性）。"""
        if self._built:
            return self._detectors
        detectors: list[Detector] = []
        for spec in self._specs:
            if not spec.enabled:
                continue
            detector = self._make_detector(spec)
            if detector is not None:
                detector.warmup()
                detectors.append(detector)
        self._detectors = detectors
        self._built = True
        return detectors

    def _make_detector(self, spec: DetectorSpec) -> Detector | None:
        if spec.type == "rule":
            patterns_file = spec.options.get(
                "patterns_file", self.opt("patterns_file", "policies/baseline/gate1_input_patterns.yaml")
            )
            return RuleDetector(patterns_file=patterns_file)

        if spec.type == "model":
            from xa_guard.detectors.model_detector import ModelDetector
            from xa_guard.detectors.backends import get_backend

            backend_name = spec.options.get("backend", "stub")
            backend_options = dict(spec.options.get("options", {}) or {})
            for key in ("model_path", "model", "device", "dry_run", "threshold", "category_map"):
                if key in spec.options and key not in backend_options:
                    backend_options[key] = spec.options[key]
            categories: list[str] | None = spec.options.get("categories")
            threshold: float = float(spec.options.get("threshold", 0.5))
            timeout_ms: int | None = spec.options.get("timeout_ms")
            category_map: dict[str, str] = {}
            category_map.update(_load_category_map(spec.options.get("category_map_file")))
            category_map.update(spec.options.get("category_map") or {})

            try:
                backend = get_backend(backend_name, backend_options)
            except KeyError:
                # 配置的后端名未注册 → 跳过，记录日志（runtime 会打 warning）
                from xa_guard.detectors.backends import list_backends
                import logging
                logging.getLogger("xa_guard.gate1").warning(
                    "detector %s: backend %r not registered (known: %s), skipping",
                    spec.name, backend_name, list_backends(),
                )
                return None

            return ModelDetector(
                backend=backend,
                categories=categories,
                threshold=threshold,
                timeout_ms=timeout_ms,
                fail_open=spec.options.get("fail_open", True),
                category_map=category_map,
            )

        # 未知类型
        import logging
        logging.getLogger("xa_guard.gate1").warning(
            "detector %s: unknown type %r, skipping", spec.name, spec.type,
        )
        return None

    # ─── 入口：evaluate ──────────────────────────────────────────────

    def evaluate(self, ctx: GateContext, stage: GateStage = GateStage.INBOUND) -> GateResult:
        detectors = self._build_detectors()

        # 1. 归一化：GateContext → DetectionInput
        inp = self._ctx_to_input(ctx)

        # 2. Spotlighting 预处理（可选）
        if self.spotlight_enabled:
            inp = apply_spotlighting(inp, ctx)

        # 3. 运行所有探测器 → DetectionResult[]
        results = []
        for detector in detectors:
            try:
                result = detector.detect(inp, ctx)
                results.append(result)
            except Exception:
                # 防御性：detect() 契约说不会抛，但万一有个不守契约的
                from xa_guard.detectors.base import DetectionResult as DR
                results.append(DR(
                    labels=[], detector_name=detector.name,
                    available=False,
                    metadata={"error": "detector_crash"},
                ))

        # 4. 融合
        decision, risks, fusion_meta = fuse(results, ctx, deny_categories=self.deny_categories)

        # 5. 来源风险加权（旧版行为保留）
        source_risk = _compute_source_risk(ctx.input_sources, self.source_weights)

        # 6. 构建 metadata（与旧版格式兼容，扩展 detector 明细）
        all_labels: list[dict[str, Any]] = []
        for r in results:
            for lbl in r.labels:
                all_labels.append({
                    "category": lbl.category,
                    "score": lbl.score,
                    "detector": lbl.detector,
                    "term": lbl.term,
                    "origin": lbl.origin,
                })

        metadata: dict[str, Any] = {
            "detected_patterns": [f"{l['category']}:{l['term']}" for l in all_labels if l["term"]],
            "source_risk_score": source_risk,
            "spotlighting": {
                "enabled": self.spotlight_enabled,
                "applied": bool(inp.meta.get("spotlighted")),
                "untrusted_sources": list(inp.meta.get("untrusted_sources", [])),
                "marked_text_length": len(str(inp.meta.get("spotlighted_text", ""))),
                "has_untrusted_source_marker": "<untrusted_source" in str(inp.meta.get("spotlighted_text", "")),
            },
            "detectors": [
                {
                    "name": r.detector_name,
                    "available": r.available,
                    "labels": len(r.labels),
                    "latency_ms": r.latency_ms,
                }
                for r in results
            ],
            "fusion": fusion_meta,
            "model_v2": True,  # 标记：v2 检测框架
            "all_labels": all_labels,
        }

        # 保留旧版 detected_patterns 兼容
        if not metadata["detected_patterns"]:
            metadata["detected_patterns"] = []

        return GateResult(
            gate_name=self.name,
            decision=decision,
            risks=risks,
            metadata=metadata,
        )

    # ─── 辅助：GateContext → DetectionInput ──────────────────────────

    def _ctx_to_input(self, ctx: GateContext) -> DetectionInput:
        """把 GateContext 拍平成 DetectionInput。

        - raw_text：保留原文（工具名+参数+历史），用于模型推理。
        - text：格式化文本，用于规则匹配（保持文本处理一致）。
        - meta：存放结构化字段（tool_name / arguments / session_history / input_sources），
                RuleDetector 取用它们做精确扫描。
        """
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

        raw_text = "\n".join(parts)
        text = raw_text.lower()

        source_values = [s.value for s in ctx.input_sources] if ctx.input_sources else ["user"]
        main_source = source_values[0]
        history_roles = [
            str(entry.get("role", "history"))
            for entry in ctx.session_history
            if isinstance(entry, dict)
        ]
        origin = "assistant" if history_roles and all(role == "assistant" for role in history_roles) else "tool"

        return DetectionInput(
            text=text,
            raw_text=raw_text,
            source=main_source,
            origin=origin,
            sources=source_values,
            meta={
                "tool_name": ctx.tool_name,
                "arguments": ctx.arguments,
                "session_history": ctx.session_history,
                "input_sources": source_values,
            },
        )
