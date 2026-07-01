"""Enterprise governance preflight for XA-Guard.

This module models the private-control-plane layer described as "Agent
Gateway": human principals, agent inventory, data domains, and lightweight
budget attribution. It is intentionally deterministic and local-file based for
the v1 demo; no SaaS or external dependency is involved.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from xa_guard.config import GovernanceConfig
from xa_guard.types import Decision, GateContext, GateResult


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return [str(value)]


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _allows(allowed: list[str], value: str) -> bool:
    if not allowed:
        return False
    return "*" in allowed or value in allowed


@dataclass(frozen=True)
class EmployeeIdentity:
    principal: str
    name: str = ""
    tenant_id: str = "default"
    department: str = ""
    roles: list[str] = field(default_factory=list)
    data_domains: list[str] = field(default_factory=list)
    allowed_agents: list[str] = field(default_factory=list)
    budget_limit_usd: float = 0.0
    spent_usd: float = 0.0
    active: bool = True

    @property
    def remaining_budget_usd(self) -> float:
        if self.budget_limit_usd <= 0:
            return float("inf")
        return max(self.budget_limit_usd - self.spent_usd, 0.0)


@dataclass(frozen=True)
class AgentIdentity:
    agent_id: str
    name: str = ""
    tenant_id: str = "default"
    owner: str = ""
    purpose: str = ""
    allowed_tools: list[str] = field(default_factory=list)
    allowed_data_domains: list[str] = field(default_factory=list)
    risk_level: str = "medium"
    max_autonomy: str = "assistive"
    requires_human_approval_for: list[str] = field(default_factory=list)
    active: bool = True


@dataclass(frozen=True)
class DataDomain:
    domain_id: str
    name: str = ""
    tenant_id: str = "default"
    sensitivity: str = "INTERNAL"
    allowed_departments: list[str] = field(default_factory=list)
    allowed_roles: list[str] = field(default_factory=list)
    allow_cross_subject_roles: list[str] = field(default_factory=list)
    requires_approval: bool = False
    active: bool = True


@dataclass(frozen=True)
class GovernanceRegistry:
    employees: dict[str, EmployeeIdentity] = field(default_factory=dict)
    agents: dict[str, AgentIdentity] = field(default_factory=dict)
    data_domains: dict[str, DataDomain] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "GovernanceRegistry":
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        default_tenant = str(raw.get("default_tenant") or "default")

        employees: dict[str, EmployeeIdentity] = {}
        for item in raw.get("employees", []) or []:
            principal = str(item.get("principal") or "")
            if not principal:
                continue
            employees[principal] = EmployeeIdentity(
                principal=principal,
                name=str(item.get("name") or ""),
                tenant_id=str(item.get("tenant_id") or default_tenant),
                department=str(item.get("department") or ""),
                roles=_as_list(item.get("roles")),
                data_domains=_as_list(item.get("data_domains")),
                allowed_agents=_as_list(item.get("allowed_agents")),
                budget_limit_usd=_as_float(item.get("budget_limit_usd")),
                spent_usd=_as_float(item.get("spent_usd")),
                active=bool(item.get("active", True)),
            )

        agents: dict[str, AgentIdentity] = {}
        for item in raw.get("agents", []) or []:
            agent_id = str(item.get("agent_id") or "")
            if not agent_id:
                continue
            agents[agent_id] = AgentIdentity(
                agent_id=agent_id,
                name=str(item.get("name") or ""),
                tenant_id=str(item.get("tenant_id") or default_tenant),
                owner=str(item.get("owner") or ""),
                purpose=str(item.get("purpose") or ""),
                allowed_tools=_as_list(item.get("allowed_tools")),
                allowed_data_domains=_as_list(item.get("allowed_data_domains")),
                risk_level=str(item.get("risk_level") or "medium"),
                max_autonomy=str(item.get("max_autonomy") or "assistive"),
                requires_human_approval_for=_as_list(item.get("requires_human_approval_for")),
                active=bool(item.get("active", True)),
            )

        domains: dict[str, DataDomain] = {}
        for item in raw.get("data_domains", []) or []:
            domain_id = str(item.get("domain_id") or "")
            if not domain_id:
                continue
            domains[domain_id] = DataDomain(
                domain_id=domain_id,
                name=str(item.get("name") or ""),
                tenant_id=str(item.get("tenant_id") or default_tenant),
                sensitivity=str(item.get("sensitivity") or "INTERNAL"),
                allowed_departments=_as_list(item.get("allowed_departments")),
                allowed_roles=_as_list(item.get("allowed_roles")),
                allow_cross_subject_roles=_as_list(item.get("allow_cross_subject_roles")),
                requires_approval=bool(item.get("requires_approval", False)),
                active=bool(item.get("active", True)),
            )

        return cls(employees=employees, agents=agents, data_domains=domains)


class GovernanceEnforcer:
    name = "governance_preflight"

    def __init__(self, cfg: GovernanceConfig) -> None:
        self.cfg = cfg
        self.enabled = bool(cfg.enabled)
        self.registry = GovernanceRegistry.from_yaml(cfg.registry_file) if self.enabled else GovernanceRegistry()

    def evaluate(self, ctx: GateContext) -> GateResult:
        if not self.enabled:
            return GateResult(gate_name=self.name, decision=Decision.ALLOW, note="disabled")

        tenant_id = ctx.tenant_id or self.cfg.default_tenant
        ctx.tenant_id = tenant_id
        principal = ctx.human_principal
        agent_id = ctx.agent_id
        data_domain = ctx.data_domain
        risks: list[str] = []
        rule_hits: list[str] = []

        def deny(rule: str, risk: str) -> GateResult:
            risks.append(risk)
            rule_hits.append(rule)
            return self._result(ctx, Decision.DENY, risks, rule_hits, tenant_id=tenant_id)

        if not principal:
            return deny("GOV-MISSING-PRINCIPAL", "missing human principal")
        if not agent_id:
            return deny("GOV-MISSING-AGENT", "missing agent identity")

        employee = self.registry.employees.get(principal)
        if employee is None or not employee.active:
            return deny("GOV-UNKNOWN-PRINCIPAL", f"unknown or inactive principal: {principal}")
        if employee.tenant_id != tenant_id:
            return deny("GOV-TENANT-MISMATCH", f"principal {principal} is outside tenant {tenant_id}")

        agent = self.registry.agents.get(agent_id)
        if agent is None or not agent.active:
            return deny("GOV-UNKNOWN-AGENT", f"unknown or inactive agent: {agent_id}")
        if agent.tenant_id != tenant_id:
            return deny("GOV-TENANT-MISMATCH", f"agent {agent_id} is outside tenant {tenant_id}")

        if not _allows(employee.allowed_agents, agent_id):
            return deny("GOV-AGENT-ASSIGNMENT", f"{principal} cannot use agent {agent_id}")

        if not _allows(agent.allowed_tools, ctx.tool_name):
            return deny("GOV-AGENT-TOOL-SCOPE", f"agent {agent_id} cannot call tool {ctx.tool_name}")

        domain: DataDomain | None = None
        if data_domain:
            domain = self.registry.data_domains.get(data_domain)
            if domain is None or not domain.active:
                return deny("GOV-UNKNOWN-DATA-DOMAIN", f"unknown or inactive data domain: {data_domain}")
            if domain.tenant_id != tenant_id:
                return deny("GOV-TENANT-MISMATCH", f"data domain {data_domain} is outside tenant {tenant_id}")
            if not self._employee_can_access_domain(employee, domain):
                return deny("GOV-EMPLOYEE-DATA-DOMAIN", f"{principal} cannot access data domain {data_domain}")
            if not _allows(agent.allowed_data_domains, data_domain):
                return deny("GOV-AGENT-DATA-DOMAIN", f"agent {agent_id} cannot access data domain {data_domain}")
            if not self._resource_owner_allowed(employee, domain, ctx.resource_owner):
                return deny(
                    "GOV-RESOURCE-OWNER-SCOPE",
                    f"{principal} cannot access resource owner {ctx.resource_owner}",
                )

        if ctx.cost_estimate_usd > employee.remaining_budget_usd:
            return deny(
                "GOV-BUDGET-EXCEEDED",
                f"estimated cost {ctx.cost_estimate_usd:.4f} exceeds remaining budget",
            )

        approval_required = False
        if domain is not None and domain.requires_approval:
            approval_required = True
            rule_hits.append("GOV-DATA-DOMAIN-APPROVAL")
            risks.append(f"data domain {data_domain} requires human approval")
        if ctx.tool_name in agent.requires_human_approval_for or data_domain in agent.requires_human_approval_for:
            approval_required = True
            rule_hits.append("GOV-AGENT-APPROVAL")
            risks.append(f"agent {agent_id} requires human approval for this scope")

        decision = Decision.REQUIRE_APPROVAL if approval_required else Decision.ALLOW
        return self._result(ctx, decision, risks, rule_hits, tenant_id=tenant_id)

    def _employee_can_access_domain(self, employee: EmployeeIdentity, domain: DataDomain) -> bool:
        if _allows(employee.data_domains, domain.domain_id):
            return True
        if employee.department and _allows(domain.allowed_departments, employee.department):
            return True
        return bool(set(employee.roles).intersection(domain.allowed_roles))

    def _resource_owner_allowed(
        self, employee: EmployeeIdentity, domain: DataDomain, resource_owner: str
    ) -> bool:
        if not resource_owner or resource_owner == employee.principal:
            return True
        return bool(set(employee.roles).intersection(domain.allow_cross_subject_roles))

    def _result(
        self,
        ctx: GateContext,
        decision: Decision,
        risks: list[str],
        rule_hits: list[str],
        *,
        tenant_id: str,
    ) -> GateResult:
        return GateResult(
            gate_name=self.name,
            decision=decision,
            risks=risks,
            rule_hits=rule_hits,
            metadata={
                "tenant_id": tenant_id,
                "human_principal": ctx.human_principal,
                "agent_id": ctx.agent_id,
                "data_domain": ctx.data_domain,
                "resource_owner": ctx.resource_owner,
                "task_id": ctx.task_id,
                "cost_estimate_usd": ctx.cost_estimate_usd,
                "output_estimate": ctx.output_estimate,
                "capability_token": dict(ctx.capability_token_summary or {}),
            },
        )
