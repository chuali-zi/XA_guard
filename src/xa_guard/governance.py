"""Static enterprise governance preflight for XA-Guard.

This module is still local-file based: it does not authenticate against SSO,
LDAP, SCIM, or a live IAM service. The v0.2 registry shape models the same
enterprise control-plane concepts statically so the runtime can enforce
tenant isolation, RBAC, ABAC, budget, approval, and auditable attribution.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from xa_guard.config import GovernanceConfig
from xa_guard.types import Decision, GateContext, GateResult


ACTIVE_STATUSES = {"active", "enabled"}
VALID_PERMISSION_ACTIONS = {"use_agent", "call_tool", "access_data_domain", "cross_subject_access"}


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


def _is_active(status: str) -> bool:
    return status.lower() in ACTIVE_STATUSES


@dataclass(frozen=True)
class Permission:
    action: str
    tools: list[str] = field(default_factory=list)
    agents: list[str] = field(default_factory=list)
    data_domains: list[str] = field(default_factory=list)
    resource_owners: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Role:
    role_id: str
    tenant_id: str = "default"
    name: str = ""
    permissions: list[Permission] = field(default_factory=list)
    status: str = "active"

    @property
    def active(self) -> bool:
        return _is_active(self.status)


@dataclass(frozen=True)
class RoleBinding:
    binding_id: str
    tenant_id: str = "default"
    role_id: str = ""
    principals: list[str] = field(default_factory=list)
    groups: list[str] = field(default_factory=list)
    status: str = "active"

    @property
    def active(self) -> bool:
        return _is_active(self.status)


@dataclass(frozen=True)
class Group:
    group_id: str
    tenant_id: str = "default"
    members: list[str] = field(default_factory=list)
    status: str = "active"

    @property
    def active(self) -> bool:
        return _is_active(self.status)


@dataclass(frozen=True)
class EmployeeIdentity:
    principal: str
    name: str = ""
    tenant_id: str = "default"
    department: str = ""
    roles: list[str] = field(default_factory=list)
    data_domains: list[str] = field(default_factory=list)
    allowed_agents: list[str] = field(default_factory=list)
    groups: list[str] = field(default_factory=list)
    manager: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)
    budget_limit_usd: float = 0.0
    spent_usd: float = 0.0
    status: str = "active"

    @property
    def active(self) -> bool:
        return _is_active(self.status)

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
    status: str = "active"

    @property
    def active(self) -> bool:
        return _is_active(self.status)


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
    status: str = "active"

    @property
    def active(self) -> bool:
        return _is_active(self.status)


@dataclass(frozen=True)
class ApprovalPolicy:
    policy_id: str
    tenant_id: str = "default"
    when: dict[str, Any] = field(default_factory=dict)
    decision: Decision = Decision.REQUIRE_APPROVAL
    reason: str = ""
    status: str = "active"

    @property
    def active(self) -> bool:
        return _is_active(self.status)


@dataclass(frozen=True)
class GovernanceRegistry:
    schema_version: str = "xa-guard-governance/v0.1"
    registry_version: str = ""
    default_tenant: str = "default"
    tenants: dict[str, dict[str, Any]] = field(default_factory=dict)
    employees: dict[str, EmployeeIdentity] = field(default_factory=dict)
    agents: dict[str, AgentIdentity] = field(default_factory=dict)
    data_domains: dict[str, DataDomain] = field(default_factory=dict)
    groups: dict[str, Group] = field(default_factory=dict)
    roles: dict[str, Role] = field(default_factory=dict)
    role_bindings: list[RoleBinding] = field(default_factory=list)
    approval_policies: list[ApprovalPolicy] = field(default_factory=list)
    budgets: dict[str, dict[str, float]] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "GovernanceRegistry":
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        schema_version = str(raw.get("schema_version") or "xa-guard-governance/v0.1")
        if schema_version.endswith("/v0.2"):
            return cls._from_v02(raw)
        return cls._from_v01(raw)

    @classmethod
    def _from_v01(cls, raw: dict[str, Any]) -> "GovernanceRegistry":
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
                status="active" if bool(item.get("active", True)) else "disabled",
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
                status="active" if bool(item.get("active", True)) else "disabled",
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
                status="active" if bool(item.get("active", True)) else "disabled",
            )

        return cls(
            schema_version=str(raw.get("schema_version") or "xa-guard-governance/v0.1"),
            registry_version=str(raw.get("registry_version") or "demo-v0.1"),
            default_tenant=default_tenant,
            tenants={default_tenant: {"tenant_id": default_tenant, "status": "active"}},
            employees=employees,
            agents=agents,
            data_domains=domains,
        )

    @classmethod
    def _from_v02(cls, raw: dict[str, Any]) -> "GovernanceRegistry":
        default_tenant = str(raw.get("default_tenant") or "default")
        tenants = {
            str(item.get("tenant_id")): dict(item)
            for item in raw.get("tenants", []) or []
            if item.get("tenant_id")
        }
        if default_tenant not in tenants:
            tenants[default_tenant] = {"tenant_id": default_tenant, "status": "active"}

        employees: dict[str, EmployeeIdentity] = {}
        for item in raw.get("principals", []) or []:
            principal = str(item.get("principal_id") or item.get("principal") or "")
            if not principal:
                raise ValueError("governance principal missing principal_id")
            if principal in employees:
                raise ValueError(f"duplicate governance principal: {principal}")
            budget = item.get("budget") or {}
            employees[principal] = EmployeeIdentity(
                principal=principal,
                name=str(item.get("display_name") or item.get("name") or ""),
                tenant_id=str(item.get("tenant_id") or default_tenant),
                department=str(item.get("department") or ""),
                roles=_as_list(item.get("roles")),
                groups=_as_list(item.get("groups")),
                data_domains=_as_list(item.get("data_domains")),
                allowed_agents=_as_list(item.get("allowed_agents")),
                manager=str(item.get("manager") or ""),
                attributes=dict(item.get("attributes") or {}),
                budget_limit_usd=_as_float(budget.get("limit_usd")),
                spent_usd=_as_float(budget.get("spent_usd")),
                status=str(item.get("status") or "active"),
            )

        groups: dict[str, Group] = {}
        for item in raw.get("groups", []) or []:
            group_id = str(item.get("group_id") or "")
            if not group_id:
                raise ValueError("governance group missing group_id")
            if group_id in groups:
                raise ValueError(f"duplicate governance group: {group_id}")
            groups[group_id] = Group(
                group_id=group_id,
                tenant_id=str(item.get("tenant_id") or default_tenant),
                members=_as_list(item.get("members")),
                status=str(item.get("status") or "active"),
            )

        budgets: dict[str, dict[str, float]] = {}
        for item in raw.get("budgets", []) or []:
            principal_id = str(item.get("principal_id") or "")
            if not principal_id:
                raise ValueError("governance budget missing principal_id")
            budgets[principal_id] = {
                "limit_usd": _as_float(item.get("limit_usd")),
                "spent_usd": _as_float(item.get("spent_usd")),
            }

        # Re-parse principal budgets after top-level budgets are available.
        if budgets:
            rebuilt: dict[str, EmployeeIdentity] = {}
            for principal in employees.values():
                budget = budgets.get(principal.principal)
                if budget is None:
                    rebuilt[principal.principal] = principal
                    continue
                rebuilt[principal.principal] = EmployeeIdentity(
                    principal=principal.principal,
                    name=principal.name,
                    tenant_id=principal.tenant_id,
                    department=principal.department,
                    roles=principal.roles,
                    data_domains=principal.data_domains,
                    allowed_agents=principal.allowed_agents,
                    groups=principal.groups,
                    manager=principal.manager,
                    attributes=principal.attributes,
                    budget_limit_usd=budget["limit_usd"],
                    spent_usd=budget["spent_usd"],
                    status=principal.status,
                )
            employees = rebuilt

        roles: dict[str, Role] = {}
        for item in raw.get("roles", []) or []:
            role_id = str(item.get("role_id") or "")
            if not role_id:
                raise ValueError("governance role missing role_id")
            if role_id in roles:
                raise ValueError(f"duplicate governance role: {role_id}")
            permissions = [_permission_from_raw(p) for p in item.get("permissions", []) or []]
            roles[role_id] = Role(
                role_id=role_id,
                tenant_id=str(item.get("tenant_id") or default_tenant),
                name=str(item.get("name") or ""),
                permissions=permissions,
                status=str(item.get("status") or "active"),
            )

        role_bindings = [
            RoleBinding(
                binding_id=str(item.get("binding_id") or f"binding-{idx}"),
                tenant_id=str(item.get("tenant_id") or default_tenant),
                role_id=str(item.get("role_id") or ""),
                principals=_as_list(item.get("principals")),
                groups=_as_list(item.get("groups")),
                status=str(item.get("status") or "active"),
            )
            for idx, item in enumerate(raw.get("role_bindings", []) or [])
        ]

        agents: dict[str, AgentIdentity] = {}
        for item in raw.get("agents", []) or []:
            agent_id = str(item.get("agent_id") or "")
            if not agent_id:
                raise ValueError("governance agent missing agent_id")
            if agent_id in agents:
                raise ValueError(f"duplicate governance agent: {agent_id}")
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
                status=str(item.get("status") or "active"),
            )

        domains: dict[str, DataDomain] = {}
        for item in raw.get("data_domains", []) or []:
            domain_id = str(item.get("domain_id") or "")
            if not domain_id:
                raise ValueError("governance data domain missing domain_id")
            if domain_id in domains:
                raise ValueError(f"duplicate governance data domain: {domain_id}")
            domains[domain_id] = DataDomain(
                domain_id=domain_id,
                name=str(item.get("name") or ""),
                tenant_id=str(item.get("tenant_id") or default_tenant),
                sensitivity=str(item.get("sensitivity") or "INTERNAL"),
                allowed_departments=_as_list(item.get("allowed_departments")),
                allowed_roles=_as_list(item.get("allowed_roles")),
                allow_cross_subject_roles=_as_list(item.get("allow_cross_subject_roles")),
                requires_approval=bool(item.get("requires_approval", False)),
                status=str(item.get("status") or "active"),
            )

        approval_policies = [
            ApprovalPolicy(
                policy_id=str(item.get("policy_id") or ""),
                tenant_id=str(item.get("tenant_id") or default_tenant),
                when=dict(item.get("when") or {}),
                decision=Decision(str(item.get("decision") or Decision.REQUIRE_APPROVAL.value)),
                reason=str(item.get("reason") or ""),
                status=str(item.get("status") or "active"),
            )
            for item in raw.get("approval_policies", []) or []
        ]
        for policy in approval_policies:
            if not policy.policy_id:
                raise ValueError("governance approval policy missing policy_id")

        registry = cls(
            schema_version=str(raw.get("schema_version") or "xa-guard-governance/v0.2"),
            registry_version=str(raw.get("registry_version") or ""),
            default_tenant=default_tenant,
            tenants=tenants,
            employees=employees,
            agents=agents,
            data_domains=domains,
            groups=groups,
            roles=roles,
            role_bindings=role_bindings,
            approval_policies=approval_policies,
            budgets=budgets,
        )
        registry.validate()
        return registry

    def validate(self) -> None:
        for principal in self.employees.values():
            if principal.tenant_id not in self.tenants:
                raise ValueError(f"principal {principal.principal} references unknown tenant {principal.tenant_id}")
            for group_id in principal.groups:
                group = self.groups.get(group_id)
                if group is None:
                    raise ValueError(f"principal {principal.principal} references unknown group {group_id}")
                if group.tenant_id != principal.tenant_id:
                    raise ValueError(f"principal {principal.principal} references cross-tenant group {group_id}")
            for role_id in principal.roles:
                role = self.roles.get(role_id)
                if role is None:
                    raise ValueError(f"principal {principal.principal} references unknown role {role_id}")
                if role.tenant_id != principal.tenant_id:
                    raise ValueError(f"principal {principal.principal} references cross-tenant role {role_id}")
            for agent_id in principal.allowed_agents:
                if agent_id != "*" and agent_id not in self.agents:
                    raise ValueError(f"principal {principal.principal} references unknown agent {agent_id}")

        for group in self.groups.values():
            if group.tenant_id not in self.tenants:
                raise ValueError(f"group {group.group_id} references unknown tenant {group.tenant_id}")
            for member in group.members:
                principal = self.employees.get(member)
                if principal is None:
                    raise ValueError(f"group {group.group_id} references unknown principal {member}")
                if principal.tenant_id != group.tenant_id:
                    raise ValueError(f"group {group.group_id} references cross-tenant principal {member}")

        for principal_id in self.budgets:
            if principal_id not in self.employees:
                raise ValueError(f"budget references unknown principal {principal_id}")

        for role in self.roles.values():
            if role.tenant_id not in self.tenants:
                raise ValueError(f"role {role.role_id} references unknown tenant {role.tenant_id}")
            for permission in role.permissions:
                if permission.action not in VALID_PERMISSION_ACTIONS:
                    raise ValueError(f"role {role.role_id} has unknown permission action {permission.action}")
                for agent_id in permission.agents:
                    if agent_id != "*" and agent_id not in self.agents:
                        raise ValueError(f"role {role.role_id} references unknown agent {agent_id}")
                for domain_id in permission.data_domains:
                    if domain_id != "*" and domain_id not in self.data_domains:
                        raise ValueError(f"role {role.role_id} references unknown data domain {domain_id}")

        for binding in self.role_bindings:
            role = self.roles.get(binding.role_id)
            if role is None:
                raise ValueError(f"role binding {binding.binding_id} references unknown role {binding.role_id}")
            if role.tenant_id != binding.tenant_id:
                raise ValueError(f"role binding {binding.binding_id} crosses tenant boundary")
            for principal_id in binding.principals:
                principal = self.employees.get(principal_id)
                if principal is None:
                    raise ValueError(f"role binding {binding.binding_id} references unknown principal {principal_id}")
                if principal.tenant_id != binding.tenant_id:
                    raise ValueError(f"role binding {binding.binding_id} references cross-tenant principal")
            for group_id in binding.groups:
                group = self.groups.get(group_id)
                if group is None:
                    raise ValueError(f"role binding {binding.binding_id} references unknown group {group_id}")
                if group.tenant_id != binding.tenant_id:
                    raise ValueError(f"role binding {binding.binding_id} references cross-tenant group")

        for agent in self.agents.values():
            if agent.tenant_id not in self.tenants:
                raise ValueError(f"agent {agent.agent_id} references unknown tenant {agent.tenant_id}")
            if not agent.allowed_tools:
                raise ValueError(f"agent {agent.agent_id} has empty allowed_tools")
            if not agent.allowed_data_domains:
                raise ValueError(f"agent {agent.agent_id} has empty allowed_data_domains")

        for domain in self.data_domains.values():
            if domain.tenant_id not in self.tenants:
                raise ValueError(f"data domain {domain.domain_id} references unknown tenant {domain.tenant_id}")


def _permission_from_raw(raw: dict[str, Any]) -> Permission:
    return Permission(
        action=str(raw.get("action") or ""),
        tools=_as_list(raw.get("tools")),
        agents=_as_list(raw.get("agents")),
        data_domains=_as_list(raw.get("data_domains")),
        resource_owners=_as_list(raw.get("resource_owners")),
    )


class GovernanceEnforcer:
    name = "governance_preflight"

    def __init__(self, cfg: GovernanceConfig) -> None:
        self.cfg = cfg
        self.enabled = bool(cfg.enabled)
        self.registry = GovernanceRegistry.from_yaml(cfg.registry_file) if self.enabled else GovernanceRegistry()

    def evaluate(self, ctx: GateContext) -> GateResult:
        if not self.enabled:
            return GateResult(gate_name=self.name, decision=Decision.ALLOW, note="disabled")

        tenant_id = ctx.tenant_id or self.cfg.default_tenant or self.registry.default_tenant
        ctx.tenant_id = tenant_id
        principal_id = ctx.human_principal
        agent_id = ctx.agent_id
        data_domain = ctx.data_domain
        risks: list[str] = []
        rule_hits: list[str] = []
        metadata: dict[str, Any] = {
            "tenant_id": tenant_id,
            "registry_version": self.registry.registry_version,
            "policy_version": self.registry.schema_version,
            "human_principal": ctx.human_principal,
            "agent_id": ctx.agent_id,
            "data_domain": ctx.data_domain,
            "resource_owner": ctx.resource_owner,
            "task_id": ctx.task_id,
            "cost_estimate_usd": ctx.cost_estimate_usd,
            "output_estimate": ctx.output_estimate,
            "capability_token": dict(ctx.capability_token_summary or {}),
        }

        def deny(rule: str, risk: str, **extra: Any) -> GateResult:
            risks.append(risk)
            rule_hits.append(rule)
            metadata.update(extra)
            metadata["decision_reason_code"] = rule
            return self._result(ctx, Decision.DENY, risks, rule_hits, metadata=metadata)

        if not principal_id:
            return deny("GOV-MISSING-PRINCIPAL", "missing human principal")
        if not agent_id:
            return deny("GOV-MISSING-AGENT", "missing agent identity")

        employee = self.registry.employees.get(principal_id)
        if employee is None or not employee.active:
            return deny("GOV-UNKNOWN-PRINCIPAL", f"unknown or inactive principal: {principal_id}")
        if employee.tenant_id != tenant_id:
            return deny("GOV-TENANT-MISMATCH", f"principal {principal_id} is outside tenant {tenant_id}")

        agent = self.registry.agents.get(agent_id)
        if agent is None or not agent.active:
            return deny("GOV-UNKNOWN-AGENT", f"unknown or inactive agent: {agent_id}")
        if agent.tenant_id != tenant_id:
            return deny("GOV-TENANT-MISMATCH", f"agent {agent_id} is outside tenant {tenant_id}")

        role_ids = self._effective_role_ids(employee)
        metadata["role_ids"] = role_ids
        if not self._can_use_agent(employee, role_ids, agent_id):
            return deny("GOV-AGENT-ASSIGNMENT", f"{principal_id} cannot use agent {agent_id}", role_ids=role_ids)

        if not self._can_call_tool(employee, role_ids, agent, ctx.tool_name):
            return deny("GOV-AGENT-TOOL-SCOPE", f"agent {agent_id} cannot call tool {ctx.tool_name}", role_ids=role_ids)

        domain: DataDomain | None = None
        if data_domain:
            domain = self.registry.data_domains.get(data_domain)
            if domain is None or not domain.active:
                return deny("GOV-UNKNOWN-DATA-DOMAIN", f"unknown or inactive data domain: {data_domain}")
            if domain.tenant_id != tenant_id:
                return deny("GOV-TENANT-MISMATCH", f"data domain {data_domain} is outside tenant {tenant_id}")
            if not self._employee_can_access_domain(employee, role_ids, domain):
                return deny("GOV-EMPLOYEE-DATA-DOMAIN", f"{principal_id} cannot access data domain {data_domain}")
            if not _allows(agent.allowed_data_domains, data_domain):
                return deny("GOV-AGENT-DATA-DOMAIN", f"agent {agent_id} cannot access data domain {data_domain}")
            if not self._resource_owner_allowed(employee, role_ids, domain, ctx.resource_owner):
                return deny("GOV-RESOURCE-OWNER-SCOPE", f"{principal_id} cannot access resource owner {ctx.resource_owner}")

        if ctx.cost_estimate_usd > employee.remaining_budget_usd:
            return deny("GOV-BUDGET-EXCEEDED", f"estimated cost {ctx.cost_estimate_usd:.4f} exceeds remaining budget")

        approval_policy_id = ""
        approval_required = False
        if domain is not None and domain.requires_approval:
            approval_required = True
            rule_hits.append("GOV-DATA-DOMAIN-APPROVAL")
            risks.append(f"data domain {data_domain} requires human approval")
        if ctx.tool_name in agent.requires_human_approval_for or data_domain in agent.requires_human_approval_for:
            approval_required = True
            rule_hits.append("GOV-AGENT-APPROVAL")
            risks.append(f"agent {agent_id} requires human approval for this scope")

        matched_policy = self._match_approval_policy(ctx, employee, agent, domain)
        if matched_policy is not None:
            approval_policy_id = matched_policy.policy_id
            metadata["approval_policy_id"] = approval_policy_id
            metadata["decision_reason_code"] = approval_policy_id
            if matched_policy.decision == Decision.DENY:
                return deny(matched_policy.policy_id, matched_policy.reason or "approval policy denied request")
            approval_required = True
            rule_hits.append(matched_policy.policy_id)
            risks.append(matched_policy.reason or "approval policy requires human approval")

        if approval_required:
            metadata.setdefault("decision_reason_code", approval_policy_id or "GOV-APPROVAL-REQUIRED")
            return self._result(ctx, Decision.REQUIRE_APPROVAL, risks, rule_hits, metadata=metadata)
        metadata["decision_reason_code"] = "GOV-ALLOW"
        return self._result(ctx, Decision.ALLOW, risks, rule_hits, metadata=metadata)

    def _effective_role_ids(self, employee: EmployeeIdentity) -> list[str]:
        roles = set(employee.roles)
        groups = set(employee.groups)
        for group in self.registry.groups.values():
            if group.active and group.tenant_id == employee.tenant_id and employee.principal in group.members:
                groups.add(group.group_id)
        for binding in self.registry.role_bindings:
            if not binding.active or binding.tenant_id != employee.tenant_id:
                continue
            if employee.principal in binding.principals or groups.intersection(binding.groups):
                roles.add(binding.role_id)
        return sorted(role for role in roles if self.registry.roles.get(role, Role(role)).active)

    def _permissions(self, role_ids: list[str], action: str) -> list[Permission]:
        permissions: list[Permission] = []
        for role_id in role_ids:
            role = self.registry.roles.get(role_id)
            if role is None or not role.active:
                continue
            permissions.extend(p for p in role.permissions if p.action == action)
        return permissions

    def _can_use_agent(self, employee: EmployeeIdentity, role_ids: list[str], agent_id: str) -> bool:
        if _allows(employee.allowed_agents, agent_id):
            return True
        return any(_allows(permission.agents, agent_id) for permission in self._permissions(role_ids, "use_agent"))

    def _can_call_tool(
        self, employee: EmployeeIdentity, role_ids: list[str], agent: AgentIdentity, tool_name: str
    ) -> bool:
        if not _allows(agent.allowed_tools, tool_name):
            return False
        if not self.registry.roles:
            return True
        return any(
            _allows(permission.tools, tool_name) and _allows(permission.agents or ["*"], agent.agent_id)
            for permission in self._permissions(role_ids, "call_tool")
        )

    def _employee_can_access_domain(
        self, employee: EmployeeIdentity, role_ids: list[str], domain: DataDomain
    ) -> bool:
        if _allows(employee.data_domains, domain.domain_id):
            return True
        if employee.department and _allows(domain.allowed_departments, employee.department):
            return True
        if bool(set(role_ids).intersection(domain.allowed_roles)):
            return True
        return any(
            _allows(permission.data_domains, domain.domain_id)
            for permission in self._permissions(role_ids, "access_data_domain")
        )

    def _resource_owner_allowed(
        self, employee: EmployeeIdentity, role_ids: list[str], domain: DataDomain, resource_owner: str
    ) -> bool:
        if not resource_owner or resource_owner == employee.principal:
            return True
        if bool(set(role_ids).intersection(domain.allow_cross_subject_roles)):
            return True
        return any(
            _allows(permission.data_domains or ["*"], domain.domain_id)
            and _allows(permission.resource_owners, resource_owner)
            for permission in self._permissions(role_ids, "cross_subject_access")
        )

    def _match_approval_policy(
        self,
        ctx: GateContext,
        employee: EmployeeIdentity,
        agent: AgentIdentity,
        domain: DataDomain | None,
    ) -> ApprovalPolicy | None:
        for policy in self.registry.approval_policies:
            if not policy.active or policy.tenant_id != employee.tenant_id:
                continue
            when = policy.when
            if when.get("sensitivity_in") and (domain is None or domain.sensitivity not in _as_list(when["sensitivity_in"])):
                continue
            if when.get("data_domains") and not _allows(_as_list(when["data_domains"]), ctx.data_domain):
                continue
            if when.get("tool_risk_in") and agent.risk_level not in _as_list(when["tool_risk_in"]):
                continue
            if when.get("max_autonomy_in") and agent.max_autonomy not in _as_list(when["max_autonomy_in"]):
                continue
            if bool(when.get("cross_subject_only")) and (
                not ctx.resource_owner or ctx.resource_owner == employee.principal
            ):
                continue
            return policy
        return None

    def _result(
        self,
        ctx: GateContext,
        decision: Decision,
        risks: list[str],
        rule_hits: list[str],
        *,
        metadata: dict[str, Any],
    ) -> GateResult:
        return GateResult(
            gate_name=self.name,
            decision=decision,
            risks=risks,
            rule_hits=rule_hits,
            metadata=metadata,
        )
