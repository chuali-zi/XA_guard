"""LayeredPolicySource — XA-Guard 双层策略源。

L0 baseline（不可变）+ L1 overlay（企业动态可写）。
对外暴露 4 类资源，被 Gate2/3/4 共享：

    .get_policy_rules()         → Gate3
    .get_tool_risks()           → Gate2
    .get_tool_capabilities()    → Gate4 INBOUND/OUTBOUND
    .get_sensitive_pattern()    → Gate4 _scan_sensitive
    .bundle_sha                 → Gate6 AuditRecord

调用契约：
- pipeline 启动时实例化一次，三个 gate 共用
- 每次 reload() 走 monotonicity 门控；失败 → 保留旧版本，返回 False + 写 audit 告警
- bundle_sha 反映"当前生效"的字节哈希，事故复盘可对齐

容错：
- baseline_manifest 缺失 → 当作无 baseline，全部空集（仅作为类型容器；旧代码仍用文件直读）
- overlay 目录缺失 → 当作无 overlay
- 任意 overlay 单调性失败 → 整批 overlay 丢弃，单租户隔离
"""
from __future__ import annotations

import hashlib
import logging
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml

from xa_guard.policy.compiler import compile_predicate as _compile_legacy
from xa_guard.policy.loader import load_policy_yaml
from xa_guard.policy.monotonicity import (
    MonotonicityReport,
    PolicyViolationError,
    check_rules,
    check_sensitive_patterns,
    check_tool_capabilities,
    check_tool_risks,
)
from xa_guard.policy.predicate_safe import (
    UnsafePredicateError,
    compile_for_tier,
)
from xa_guard.types import (
    PolicyRule,
    RiskLevel,
    TaintLabel,
    ToolCapability,
)

log = logging.getLogger("xa_guard.policy.layered")


# ============================================================
# 数据容器
# ============================================================
@dataclass(frozen=True)
class _CompiledLayer:
    rules: list[PolicyRule] = field(default_factory=list)
    compiled: dict[str, Callable] = field(default_factory=dict)
    tool_risks: dict[str, RiskLevel] = field(default_factory=dict)
    tool_caps: dict[str, ToolCapability] = field(default_factory=dict)
    sensitive_patterns: list[str] = field(default_factory=list)
    # 来源标记，用于 audit / 调试
    source_files: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _Snapshot:
    """LayeredPolicySource 在某一时刻的不可变快照。reload 时原子替换。"""

    baseline: _CompiledLayer
    overlays: dict[str, _CompiledLayer]            # tenant_id → layer
    merged_rules: list[PolicyRule]
    merged_compiled: dict[str, Callable]
    merged_tool_risks: dict[str, RiskLevel]
    merged_tool_caps: dict[str, ToolCapability]
    merged_sensitive_patterns: list[str]
    merged_pattern: re.Pattern | None
    bundle_sha: str
    overlay_rejections: dict[str, str] = field(default_factory=dict)


# ============================================================
# 单层加载（baseline 或单个 overlay 子目录）
# ============================================================
def _safe_load_yaml(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}


def _load_rules(path: Path, tier: str) -> tuple[list[PolicyRule], dict[str, Callable]]:
    if not path.exists():
        return [], {}
    rules = load_policy_yaml(path)
    compiled: dict[str, Callable] = {}
    for r in rules:
        try:
            compiled[r.id] = compile_for_tier(r.predicate, tier)
        except UnsafePredicateError as exc:
            log.warning("predicate rejected (%s tier): %s", tier, exc)
            raise
    return rules, compiled


def _load_tool_risks_file(path: Path) -> dict[str, RiskLevel]:
    raw = _safe_load_yaml(path)
    mapping = raw.get("tool_risks", raw)
    out: dict[str, RiskLevel] = {}
    for name, level in (mapping or {}).items():
        try:
            out[name] = RiskLevel(str(level).lower())
        except ValueError:
            log.warning("unknown risk level for tool %s: %r", name, level)
    return out


def _load_tool_caps_file(path: Path) -> dict[str, ToolCapability]:
    raw = _safe_load_yaml(path)
    out: dict[str, ToolCapability] = {}
    for item in raw.get("tools", []) or []:
        name = item["tool_name"]
        out[name] = ToolCapability(
            tool_name=name,
            capabilities=list(item.get("capabilities", [])),
            input_max_taint=TaintLabel(item.get("input_max_taint", "CONFIDENTIAL")),
            output_taint=TaintLabel(item.get("output_taint", "PUBLIC")),
            risk_level=RiskLevel(item.get("risk_level", "green")),
            description=item.get("description", ""),
        )
    return out


def _load_sensitive_patterns_file(path: Path) -> list[str]:
    raw = _safe_load_yaml(path)
    pats = raw.get("patterns", [])
    return [str(p) for p in pats]


def _derive_tool_risks_from_caps(caps: dict[str, "ToolCapability"]) -> dict[str, RiskLevel]:
    """从工具能力表派生 risk_level 映射。
    gate4_capabilities.yaml 是全项目 risk_level 的唯一事实源；
    gate2/gate3 运行时所需 risk 均由此派生，不再读独立的 gate2_tool_risks.yaml。
    分级法规依据见 docs/risk_classification_basis.md。
    """
    return {name: cap.risk_level for name, cap in caps.items()}


def _compile_layer(
    *,
    rules_path: Path | None,
    risks_path: Path | None,
    caps_path: Path | None,
    patterns_path: Path | None,
    tier: str,
) -> _CompiledLayer:
    rules: list[PolicyRule] = []
    compiled: dict[str, Callable] = {}
    risks: dict[str, RiskLevel] = {}
    caps: dict[str, ToolCapability] = {}
    pats: list[str] = []
    files: list[str] = []

    if rules_path is not None and rules_path.exists():
        rules, compiled = _load_rules(rules_path, tier)
        files.append(str(rules_path))
    if risks_path is not None and risks_path.exists():
        # risks_path 仍接受 overlay 的独立 tool_risks.yaml（用于租户级单调性检验）
        risks = _load_tool_risks_file(risks_path)
        files.append(str(risks_path))
    if caps_path is not None and caps_path.exists():
        caps = _load_tool_caps_file(caps_path)
        files.append(str(caps_path))
        # 若 caps 已加载且本层未提供独立 risks_path（即 baseline 层），
        # 则用 caps 中的 risk_level 覆盖/补全 risks——实现单一事实源。
        # 详见 docs/risk_classification_basis.md。
        if not risks:
            risks = _derive_tool_risks_from_caps(caps)
        else:
            # 即使提供了独立 risks_path（overlay 层），也用 caps 合并补全未覆盖工具
            for name, cap in caps.items():
                if name not in risks:
                    risks[name] = cap.risk_level
    if patterns_path is not None and patterns_path.exists():
        pats = _load_sensitive_patterns_file(patterns_path)
        files.append(str(patterns_path))

    return _CompiledLayer(
        rules=rules,
        compiled=compiled,
        tool_risks=risks,
        tool_caps=caps,
        sensitive_patterns=pats,
        source_files=files,
    )


# ============================================================
# bundle_sha 计算（用于审计版本号）
# ============================================================
def _compute_bundle_sha(layers: list[_CompiledLayer]) -> str:
    h = hashlib.sha256()
    for layer in layers:
        for f in sorted(layer.source_files):
            try:
                h.update(f.encode("utf-8"))
                h.update(b"\x00")
                h.update(Path(f).read_bytes())
                h.update(b"\x00")
            except FileNotFoundError:
                continue
    return h.hexdigest()


# ============================================================
# Pattern 合并
# ============================================================
def _compile_pattern(patterns: list[str], case_insensitive: bool = True) -> re.Pattern | None:
    if not patterns:
        return None
    flags = re.IGNORECASE if case_insensitive else 0
    union = "|".join(f"(?:{p})" for p in patterns)
    try:
        return re.compile(union, flags)
    except re.error as exc:
        log.error("sensitive pattern compile failed: %s", exc)
        return None


# ============================================================
# 主类
# ============================================================
class LayeredPolicySource:
    def __init__(
        self,
        manifest_path: str | Path | None = "policies/baseline/manifest.yaml",
        overlay_root: str | Path | None = "policies/overlay",
        *,
        project_root: str | Path | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._project_root = (
            Path(project_root).resolve()
            if project_root is not None
            else Path(__file__).resolve().parents[3]
        )
        self._manifest_path = (
            self._resolve(manifest_path) if manifest_path else None
        )
        self._overlay_root = (
            self._resolve(overlay_root) if overlay_root else None
        )
        self._snapshot: _Snapshot = self._build_snapshot()

    # ------- 路径解析 --------
    def _resolve(self, p: str | Path) -> Path:
        path = Path(p)
        if path.is_absolute():
            return path
        return (self._project_root / path).resolve()

    # ------- baseline 加载 --------
    def _load_baseline(self) -> _CompiledLayer:
        if self._manifest_path is None or not self._manifest_path.exists():
            log.info("baseline manifest missing — empty baseline layer")
            return _CompiledLayer()
        raw = _safe_load_yaml(self._manifest_path)
        res = raw.get("resources", {}) or {}
        rules_path = self._resolve(res.get("policy_rules", {}).get("file", "")) \
            if res.get("policy_rules") else None
        risks_path = self._resolve(res.get("tool_risks", {}).get("file", "")) \
            if res.get("tool_risks") else None
        caps_path = self._resolve(res.get("tool_capabilities", {}).get("file", "")) \
            if res.get("tool_capabilities") else None
        patterns_path = self._resolve(res.get("sensitive_patterns", {}).get("file", "")) \
            if res.get("sensitive_patterns") else None
        return _compile_layer(
            rules_path=rules_path,
            risks_path=risks_path,
            caps_path=caps_path,
            patterns_path=patterns_path,
            tier="baseline",
        )

    # ------- overlay 加载 --------
    def _load_overlays(self) -> tuple[dict[str, _CompiledLayer], dict[str, str]]:
        out: dict[str, _CompiledLayer] = {}
        rejections: dict[str, str] = {}
        if self._overlay_root is None or not self._overlay_root.exists():
            return out, rejections
        for child in sorted(self._overlay_root.iterdir()):
            if not child.is_dir():
                continue
            tenant_id = child.name
            if tenant_id.startswith("_") or tenant_id.startswith("."):
                continue  # _template / .gitkeep 等
            try:
                layer = _compile_layer(
                    rules_path=child / "policy.yaml",
                    risks_path=child / "tool_risks.yaml",
                    caps_path=child / "tool_capabilities.yaml",
                    patterns_path=child / "sensitive_patterns.yaml",
                    tier="overlay",
                )
                out[tenant_id] = layer
            except (UnsafePredicateError, KeyError, ValueError) as exc:
                rejections[tenant_id] = f"load_error: {exc}"
                log.warning("overlay '%s' rejected at load: %s", tenant_id, exc)
        return out, rejections

    # ------- 单调性合并 --------
    def _merge_with_monotonicity(
        self,
        baseline: _CompiledLayer,
        overlays: dict[str, _CompiledLayer],
        rejections: dict[str, str],
    ) -> tuple[
        list[PolicyRule],
        dict[str, Callable],
        dict[str, RiskLevel],
        dict[str, ToolCapability],
        list[str],
    ]:
        merged_rules: list[PolicyRule] = list(baseline.rules)
        merged_compiled: dict[str, Callable] = dict(baseline.compiled)
        merged_risks: dict[str, RiskLevel] = dict(baseline.tool_risks)
        merged_caps: dict[str, ToolCapability] = dict(baseline.tool_caps)
        merged_pats: list[str] = list(baseline.sensitive_patterns)

        accepted_overlays: dict[str, _CompiledLayer] = {}

        for tenant_id, layer in overlays.items():
            reports: list[MonotonicityReport] = [
                check_rules(baseline.rules, layer.rules, tenant_id=tenant_id),
                check_tool_risks(baseline.tool_risks, layer.tool_risks),
                check_tool_capabilities(baseline.tool_caps, layer.tool_caps),
                check_sensitive_patterns(baseline.sensitive_patterns, layer.sensitive_patterns),
            ]
            all_violations: list[str] = []
            for rep in reports:
                if not rep.ok:
                    all_violations.extend(rep.violations)
            if all_violations:
                rejections[tenant_id] = "monotonicity_violation: " + "; ".join(all_violations)
                log.warning("overlay '%s' rejected by monotonicity: %s",
                            tenant_id, all_violations)
                continue
            accepted_overlays[tenant_id] = layer

        # 接受的 overlay 全部并入
        for tenant_id, layer in accepted_overlays.items():
            merged_rules.extend(layer.rules)
            merged_compiled.update(layer.compiled)
            merged_risks.update(layer.tool_risks)
            merged_caps.update(layer.tool_caps)
            merged_pats.extend(layer.sensitive_patterns)

        return merged_rules, merged_compiled, merged_risks, merged_caps, merged_pats

    # ------- 完整 snapshot 构建 --------
    def _build_snapshot(self) -> _Snapshot:
        baseline = self._load_baseline()
        overlays, rejections = self._load_overlays()
        (
            merged_rules,
            merged_compiled,
            merged_risks,
            merged_caps,
            merged_pats,
        ) = self._merge_with_monotonicity(baseline, overlays, rejections)

        bundle_sha = _compute_bundle_sha([baseline, *overlays.values()])
        merged_pattern = _compile_pattern(merged_pats, case_insensitive=True)

        return _Snapshot(
            baseline=baseline,
            overlays=overlays,
            merged_rules=merged_rules,
            merged_compiled=merged_compiled,
            merged_tool_risks=merged_risks,
            merged_tool_caps=merged_caps,
            merged_sensitive_patterns=merged_pats,
            merged_pattern=merged_pattern,
            bundle_sha=bundle_sha,
            overlay_rejections=rejections,
        )

    # ============================================================
    # 公开 API（gate2/3/4 用）
    # ============================================================
    @property
    def bundle_sha(self) -> str:
        with self._lock:
            return self._snapshot.bundle_sha

    @property
    def overlay_rejections(self) -> dict[str, str]:
        with self._lock:
            return dict(self._snapshot.overlay_rejections)

    def get_policy_rules(self) -> list[PolicyRule]:
        with self._lock:
            return list(self._snapshot.merged_rules)

    def get_compiled_predicates(self) -> dict[str, Callable]:
        with self._lock:
            return dict(self._snapshot.merged_compiled)

    def get_tool_risks(self) -> dict[str, RiskLevel]:
        with self._lock:
            return dict(self._snapshot.merged_tool_risks)

    def get_tool_capabilities(self) -> dict[str, ToolCapability]:
        with self._lock:
            return dict(self._snapshot.merged_tool_caps)

    def get_sensitive_pattern(self) -> re.Pattern | None:
        with self._lock:
            return self._snapshot.merged_pattern

    def get_sensitive_patterns(self) -> list[str]:
        with self._lock:
            return list(self._snapshot.merged_sensitive_patterns)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            s = self._snapshot
            return {
                "bundle_sha": s.bundle_sha,
                "baseline_rules": len(s.baseline.rules),
                "overlay_tenants_accepted": len(s.overlays) - len(s.overlay_rejections),
                "overlay_tenants_rejected": len(s.overlay_rejections),
                "merged_rules": len(s.merged_rules),
                "merged_tool_risks": len(s.merged_tool_risks),
                "merged_tool_caps": len(s.merged_tool_caps),
                "merged_sensitive_patterns": len(s.merged_sensitive_patterns),
            }

    # ============================================================
    # 热加载（atomic ref swap + fail-safe）
    # ============================================================
    def reload(self) -> bool:
        """重新加载 baseline + overlay。失败保留旧 snapshot，返回 False。"""
        try:
            new_snapshot = self._build_snapshot()
        except PolicyViolationError as exc:
            log.error("policy reload rejected: %s", exc)
            return False
        except Exception as exc:  # pragma: no cover - defensive
            log.exception("policy reload failed: %s", exc)
            return False
        with self._lock:
            self._snapshot = new_snapshot
        return True


# 进程级单例，供 gate2/3/4 共享
_GLOBAL_SOURCE: LayeredPolicySource | None = None


def get_global_source() -> LayeredPolicySource | None:
    return _GLOBAL_SOURCE


def set_global_source(src: LayeredPolicySource | None) -> None:
    global _GLOBAL_SOURCE
    _GLOBAL_SOURCE = src
