"""关卡 3 · 规则引擎（中文 Policy DSL） — 赛题方向 2 + 应用价值核心。

加载 policies/enterprise-l3.yaml（>=10 条 seed 规则）→ 编译每条 predicate →
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
from xa_guard.policy.loader import load_policy_yaml
from xa_guard.types import Decision, GateContext, GateResult, PolicyRule

_SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


class Gate3Policy(Gate):
    name = "gate3_policy"
    supported_stages = (GateStage.INBOUND,)

    rules: list[PolicyRule]
    compiled: dict[str, Callable[[GateContext], bool]]
    backend: str

    def __init__(self, cfg=None) -> None:
        super().__init__(cfg)
        self.backend = str(self.opt("backend", "python")).lower()
        self.rules = []
        self.compiled = {}
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
            raise NotImplementedError("rego backend reserved for M3 (OPA)")
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

    def evaluate(self, ctx: GateContext, stage: GateStage = GateStage.INBOUND) -> GateResult:
        if not self.rules:
            return GateResult(
                gate_name=self.name,
                decision=Decision.ALLOW,
                metadata={"policy_count": 0},
                note="no policies loaded",
            )

        hits: list[PolicyRule] = []
        for rule in self.rules:
            if not self._triggered(rule, ctx.tool_name):
                continue
            fn = self.compiled.get(rule.id)
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
                "policy_count": len(self.rules),
                "policy_hit_count": len(hits),
                "policy_severity_max": severity_max if hits else "none",
                "backend": self.backend,
            },
        )
