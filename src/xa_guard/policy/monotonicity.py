"""单调性门控 — overlay 不得弱化 baseline。

设计思想：业界对标
- AWS SCP：Deny 永远优先于 IAM Allow
- Google Model Armor Floor Settings：所有 template 不得低于 floor 阈值
- Kubernetes Gatekeeper ConstraintTemplate：逻辑写死，租户只填参数

红线规则（违反任意一条 → PolicyViolationError，整批 overlay 拒绝加载）：
1. rule.id 命中 baseline → 不允许 overlay 覆盖国标规则
2. tool_risks 同名工具等级从严降到松（red→green/yellow→green/red→yellow）
3. tool_capabilities 同名工具 input_max_taint 放宽（PUBLIC→INTERNAL→CONFIDENTIAL 方向）
4. sensitive_patterns overlay 不能"包含" baseline 中已存在的正则（防止"我删一条"的伪装）

调用方：layered.LayeredPolicySource._merge_*；启动期 + 每次 reload 都跑一次。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from xa_guard.types import PolicyRule, RiskLevel, TaintLabel, ToolCapability

_RISK_RANK = {RiskLevel.GREEN: 0, RiskLevel.YELLOW: 1, RiskLevel.RED: 2}
_TAINT_RANK = {TaintLabel.PUBLIC: 0, TaintLabel.INTERNAL: 1, TaintLabel.CONFIDENTIAL: 2}


class PolicyViolationError(ValueError):
    """overlay 违反单调性。拒绝整批加载，保留旧版本。"""


@dataclass
class MonotonicityReport:
    ok: bool
    violations: list[str]

    def raise_if_violated(self) -> None:
        if not self.ok:
            raise PolicyViolationError(
                "overlay rejected: " + "; ".join(self.violations)
            )


def check_rules(
    baseline_rules: Iterable[PolicyRule],
    overlay_rules: Iterable[PolicyRule],
    *,
    tenant_id: str,
) -> MonotonicityReport:
    """Gate3 规则单调性。

    - overlay 不能用 baseline 的 rule.id（视为覆盖企图）
    - overlay 的 rule.id 必须以 `tenant::<tenant_id>::` 开头
    """
    baseline_ids = {r.id for r in baseline_rules}
    expected_prefix = f"tenant::{tenant_id}::"
    violations: list[str] = []

    for rule in overlay_rules:
        if rule.id in baseline_ids:
            violations.append(
                f"rule.id '{rule.id}' collides with baseline; overlay cannot override"
            )
        if not rule.id.startswith(expected_prefix):
            violations.append(
                f"rule.id '{rule.id}' missing required prefix '{expected_prefix}'"
            )

    return MonotonicityReport(ok=not violations, violations=violations)


def check_tool_risks(
    baseline: dict[str, RiskLevel],
    overlay: dict[str, RiskLevel],
) -> MonotonicityReport:
    """Gate2 工具风险单调性 — overlay 只能持平或 ↑（更严），不能 ↓（更松）。"""
    violations: list[str] = []
    for tool, level in overlay.items():
        base = baseline.get(tool)
        if base is None:
            continue  # overlay 新增工具，允许
        if _RISK_RANK[level] < _RISK_RANK[base]:
            violations.append(
                f"tool '{tool}' risk weakened {base.value} → {level.value} (overlay must be ≥ baseline)"
            )
    return MonotonicityReport(ok=not violations, violations=violations)


def check_tool_capabilities(
    baseline: dict[str, ToolCapability],
    overlay: dict[str, ToolCapability],
) -> MonotonicityReport:
    """Gate4 工具能力单调性。

    - input_max_taint：overlay 只能 ↓（更收紧），不能 ↑（放宽接收上限）
    - capabilities：overlay 不得移除 baseline 已声明的危险能力（如 NETWORK_EXTERNAL）
    - risk_level：同 tool_risks 的方向（不能弱化）
    """
    violations: list[str] = []
    for tool, ov in overlay.items():
        base = baseline.get(tool)
        if base is None:
            continue
        if _TAINT_RANK[ov.input_max_taint] > _TAINT_RANK[base.input_max_taint]:
            violations.append(
                f"tool '{tool}' input_max_taint relaxed "
                f"{base.input_max_taint.value} → {ov.input_max_taint.value}"
            )
        # capabilities：overlay 只能是 baseline 的超集（不能缩小能力声明面）
        # ——但允许 overlay 增加（"我们这工具其实还能做 NOTIFY"）
        missing = set(base.capabilities) - set(ov.capabilities)
        if missing:
            violations.append(
                f"tool '{tool}' missing baseline capabilities {sorted(missing)}"
            )
        if _RISK_RANK[ov.risk_level] < _RISK_RANK[base.risk_level]:
            violations.append(
                f"tool '{tool}' risk_level weakened "
                f"{base.risk_level.value} → {ov.risk_level.value}"
            )
    return MonotonicityReport(ok=not violations, violations=violations)


def check_sensitive_patterns(
    baseline: list[str],
    overlay: list[str],
) -> MonotonicityReport:
    """敏感词层 — overlay 只能 ADD。不要求显式枚举 baseline，
    但任何 overlay 模式必须不能与 baseline 同名（无意义的副本）。
    """
    violations: list[str] = []
    base_set = set(baseline)
    for pat in overlay:
        if pat in base_set:
            violations.append(
                f"sensitive pattern '{pat}' duplicates baseline; overlay only adds"
            )
    return MonotonicityReport(ok=not violations, violations=violations)
