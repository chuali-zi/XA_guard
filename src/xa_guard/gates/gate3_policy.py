"""关卡 3 · 规则引擎（中文 Policy DSL） — 赛题方向 2 + 应用价值核心。

加载 policies/baseline/gate3_rules.yaml（>=10 条 seed 规则）→ 编译每条 predicate →
针对 GateContext 逐条评估命中 → 聚合 enforce 决策。

聚合优先级（高 → 低）：DENY > REQUIRE_APPROVAL > WARN > ALLOW。

predicate 表达式可用变量见 policy.compiler：tool / args / role / taint / risk /
sources / contains()。

关于 OPA：demo 阶段 backend=python（implementation-notes Q9）；M3 切 rego。
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from xa_guard.gates.base import Gate, GateStage
from xa_guard.policy.compiler import compile_predicate
from xa_guard.policy.layered import get_global_source
from xa_guard.policy.loader import load_policy_yaml
from xa_guard.policy.rego import RegoCompileError, RegoPolicyEngine
from xa_guard.types import Decision, GateContext, GateResult, PolicyRule

_SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


class Gate3Policy(Gate):
    name = "gate3_policy"
    supported_stages = (GateStage.INBOUND,)

    rules: list[PolicyRule]
    compiled: dict[str, Callable[[GateContext], bool]]
    backend: str
    rego: RegoPolicyEngine | None
    _layered_rego: RegoPolicyEngine | None
    _layered_rego_bundle_sha: str

    def __init__(self, cfg=None) -> None:
        super().__init__(cfg)
        self.backend = str(self.opt("backend", "python")).lower()
        self.rules = []
        self.compiled = {}
        self.rego = None
        self._layered_rego = None
        self._layered_rego_bundle_sha = ""
        policy_file = self.opt("policy_file")
        if policy_file:
            self._load(policy_file)

    def _load(self, policy_file: str | Path) -> None:
        if not Path(policy_file).exists():
            return
        self.rules = load_policy_yaml(policy_file)
        if self.backend == "python":
            self.compiled = {r.id: compile_predicate(r.predicate) for r in self.rules}
        elif self.backend == "rego":
            self.rego = RegoPolicyEngine(
                self.rules,
                opa_path=self.opt("opa_path"),
                timeout_seconds=float(self.opt("opa_timeout_seconds", 5.0)),
            )
            if bool(self.opt("strict_opa", False)) and not self.rego.opa_available:
                raise RuntimeError("gate3 rego backend requires an OPA binary when strict_opa=true")
        else:
            raise ValueError(f"unknown gate3 backend: {self.backend}")

    @staticmethod
    def _aggregate(decisions: list[Decision]) -> Decision:
        if Decision.DENY in decisions:
            return Decision.DENY
        if Decision.REQUIRE_APPROVAL in decisions:
            return Decision.REQUIRE_APPROVAL
        if Decision.WARN in decisions:
            return Decision.WARN
        return Decision.ALLOW

    def _triggered(self, rule: PolicyRule, tool_name: str) -> bool:
        # 空 triggers 视为匹配所有工具
        if not rule.triggers:
            return True
        return tool_name in rule.triggers

    def _current_view(self) -> tuple[list[PolicyRule], dict[str, Callable[[GateContext], bool]], str]:
        """LayeredPolicySource opt-in（cfg.gate3.prefer_layered: true）；默认 legacy。"""
        if bool(self.opt("prefer_layered", False)):
            layered = get_global_source()
            if layered is not None:
                rules = layered.get_policy_rules()
                if rules:
                    expected = str(self.opt("expected_policy_bundle_sha", "") or "")
                    if expected and layered.bundle_sha != expected:
                        raise RuntimeError("gate3 policy bundle drift detected")
                    return rules, layered.get_compiled_predicates(), layered.bundle_sha
        return self.rules, self.compiled, ""

    def _layered_rego_engine(self, rules: list[PolicyRule], bundle_sha: str) -> RegoPolicyEngine | None:
        if not bundle_sha:
            return None
        if self._layered_rego is not None and self._layered_rego_bundle_sha == bundle_sha:
            return self._layered_rego
        try:
            self._layered_rego = RegoPolicyEngine(
                rules,
                opa_path=self.opt("opa_path"),
                timeout_seconds=float(self.opt("opa_timeout_seconds", 5.0)),
            )
        except RegoCompileError:
            self._layered_rego = None
            self._layered_rego_bundle_sha = ""
            return None
        self._layered_rego_bundle_sha = bundle_sha
        return self._layered_rego

    def evaluate(self, ctx: GateContext, stage: GateStage = GateStage.INBOUND) -> GateResult:
        rules, compiled, bundle_sha = self._current_view()
        if not rules:
            return GateResult(
                gate_name=self.name,
                decision=Decision.ALLOW,
                metadata={"policy_count": 0},
                note="no policies loaded",
            )

        hits: list[PolicyRule] = []
        active_rego = None
        if self.backend == "rego":
            if rules is self.rules:
                active_rego = self.rego
            elif bundle_sha:
                active_rego = self._layered_rego_engine(rules, bundle_sha)
        if active_rego is not None:
            hit_ids = set(active_rego.evaluate_hits(ctx))
            hits = [rule for rule in rules if rule.id in hit_ids and self._triggered(rule, ctx.tool_name)]
        else:
            for rule in rules:
                if not self._triggered(rule, ctx.tool_name):
                    continue
                fn = compiled.get(rule.id)
                if fn is None:
                    continue
                try:
                    matched = fn(ctx)
                except Exception:
                    # predicate 异常视为未命中，避免单条规则崩 gate
                    matched = False
                if matched:
                    hits.append(rule)

        decision = self._aggregate([r.enforce for r in hits])
        severity_max = "low"
        for r in hits:
            if _SEVERITY_RANK[r.severity] > _SEVERITY_RANK[severity_max]:
                severity_max = r.severity

        return GateResult(
            gate_name=self.name,
            decision=decision,
            risks=[r.name for r in hits],
            rule_hits=[r.id for r in hits],
            metadata={
                "policy_count": len(rules),
                "policy_hit_count": len(hits),
                "policy_severity_max": severity_max if hits else "none",
                "backend": self.backend,
                "rego_mode": active_rego.mode if active_rego is not None else "",
                "opa_available": active_rego.opa_available if active_rego is not None else False,
                "policy_bundle_sha": bundle_sha,
            },
        )
