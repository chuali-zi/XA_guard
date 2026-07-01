from __future__ import annotations

import asyncio
import json
from pathlib import Path

from xa_guard.config import GateConfig, GovernanceConfig
from xa_guard.gates.base import Gate, GateStage
from xa_guard.gates.gate3_policy import Gate3Policy
from xa_guard.gates.gate6_audit import Gate6Audit
from xa_guard.governance import GovernanceEnforcer, GovernanceRegistry
from xa_guard.pipeline import Pipeline
from xa_guard.types import Decision, GateContext, GateResult


REGISTRY = Path("configs/governance.demo.yaml")


class _AllowGate(Gate):
    supported_stages = (GateStage.INBOUND, GateStage.OUTBOUND)

    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name

    def evaluate(self, ctx: GateContext, stage: GateStage = GateStage.INBOUND) -> GateResult:
        return GateResult(gate_name=self.name, decision=Decision.ALLOW)


def _ctx(**kwargs) -> GateContext:
    defaults = {
        "tool_name": "echo",
        "arguments": {"text": "hello"},
        "tenant_id": "acme-corp",
        "human_principal": "bob.dev@acme.local",
        "agent_id": "general-office-agent",
        "data_domain": "engineering_docs",
        "resource_owner": "bob.dev@acme.local",
        "task_id": "task-1",
        "cost_estimate_usd": 0.20,
    }
    defaults.update(kwargs)
    return GateContext(**defaults)


def test_governance_registry_loads_enterprise_assets():
    registry = GovernanceRegistry.from_yaml(REGISTRY)

    assert "alice.hr@acme.local" in registry.employees
    assert registry.employees["alice.hr@acme.local"].department == "HR"
    assert registry.agents["hr-assistant"].allowed_data_domains == ["employee_profile", "payroll"]
    assert registry.data_domains["payroll"].requires_approval is True


def test_unknown_agent_fails_closed():
    enforcer = GovernanceEnforcer(GovernanceConfig(enabled=True, registry_file=str(REGISTRY), default_tenant="acme-corp"))
    result = enforcer.evaluate(_ctx(agent_id="missing-agent"))

    assert result.decision == Decision.DENY
    assert result.rule_hits == ["GOV-UNKNOWN-AGENT"]


def test_employee_without_data_domain_is_denied():
    enforcer = GovernanceEnforcer(GovernanceConfig(enabled=True, registry_file=str(REGISTRY), default_tenant="acme-corp"))
    result = enforcer.evaluate(_ctx(data_domain="payroll", resource_owner="all"))

    assert result.decision == Decision.DENY
    assert "GOV-EMPLOYEE-DATA-DOMAIN" in result.rule_hits


def test_agent_tool_scope_is_denied():
    enforcer = GovernanceEnforcer(GovernanceConfig(enabled=True, registry_file=str(REGISTRY), default_tenant="acme-corp"))
    result = enforcer.evaluate(_ctx(tool_name="exec_command"))

    assert result.decision == Decision.DENY
    assert result.rule_hits == ["GOV-AGENT-TOOL-SCOPE"]


def test_empty_allow_lists_fail_closed(tmp_path):
    registry = tmp_path / "governance.yaml"
    registry.write_text(
        """
default_tenant: acme-corp
employees:
  - principal: eve.ops@acme.local
    tenant_id: acme-corp
    data_domains: [engineering_docs]
agents:
  - agent_id: unscoped-agent
    tenant_id: acme-corp
    allowed_data_domains: [engineering_docs]
data_domains:
  - domain_id: engineering_docs
    tenant_id: acme-corp
""",
        encoding="utf-8",
    )
    enforcer = GovernanceEnforcer(
        GovernanceConfig(enabled=True, registry_file=str(registry), default_tenant="acme-corp")
    )

    result = enforcer.evaluate(
        _ctx(
            human_principal="eve.ops@acme.local",
            agent_id="unscoped-agent",
            data_domain="engineering_docs",
        )
    )

    assert result.decision == Decision.DENY
    assert result.rule_hits == ["GOV-AGENT-ASSIGNMENT"]


def test_explicit_wildcard_allow_lists_are_allowed(tmp_path):
    registry = tmp_path / "governance.yaml"
    registry.write_text(
        """
default_tenant: acme-corp
employees:
  - principal: eve.ops@acme.local
    tenant_id: acme-corp
    data_domains: [engineering_docs]
    allowed_agents: ["*"]
agents:
  - agent_id: wildcard-agent
    tenant_id: acme-corp
    allowed_tools: ["*"]
    allowed_data_domains: ["*"]
data_domains:
  - domain_id: engineering_docs
    tenant_id: acme-corp
""",
        encoding="utf-8",
    )
    enforcer = GovernanceEnforcer(
        GovernanceConfig(enabled=True, registry_file=str(registry), default_tenant="acme-corp")
    )

    result = enforcer.evaluate(
        _ctx(
            human_principal="eve.ops@acme.local",
            agent_id="wildcard-agent",
            data_domain="engineering_docs",
            resource_owner="eve.ops@acme.local",
        )
    )

    assert result.decision == Decision.ALLOW


def test_all_resource_owner_requires_cross_subject_role():
    enforcer = GovernanceEnforcer(GovernanceConfig(enabled=True, registry_file=str(REGISTRY), default_tenant="acme-corp"))
    result = enforcer.evaluate(_ctx(data_domain="engineering_docs", resource_owner="all"))

    assert result.decision == Decision.DENY
    assert result.rule_hits == ["GOV-RESOURCE-OWNER-SCOPE"]


def test_hr_payroll_access_requires_approval():
    enforcer = GovernanceEnforcer(GovernanceConfig(enabled=True, registry_file=str(REGISTRY), default_tenant="acme-corp"))
    result = enforcer.evaluate(
        _ctx(
            human_principal="alice.hr@acme.local",
            agent_id="hr-assistant",
            data_domain="payroll",
            resource_owner="bob.dev@acme.local",
            cost_estimate_usd=0.50,
        )
    )

    assert result.decision == Decision.REQUIRE_APPROVAL
    assert "GOV-DATA-DOMAIN-APPROVAL" in result.rule_hits


def test_hr_cross_subject_all_resource_owner_requires_approval():
    enforcer = GovernanceEnforcer(GovernanceConfig(enabled=True, registry_file=str(REGISTRY), default_tenant="acme-corp"))
    result = enforcer.evaluate(
        _ctx(
            human_principal="alice.hr@acme.local",
            agent_id="hr-assistant",
            data_domain="payroll",
            resource_owner="all",
            cost_estimate_usd=0.50,
        )
    )

    assert result.decision == Decision.REQUIRE_APPROVAL
    assert "GOV-RESOURCE-OWNER-SCOPE" not in result.rule_hits
    assert "GOV-DATA-DOMAIN-APPROVAL" in result.rule_hits


def test_default_tenant_is_written_back_to_context():
    enforcer = GovernanceEnforcer(GovernanceConfig(enabled=True, registry_file=str(REGISTRY), default_tenant="acme-corp"))
    ctx = _ctx(tenant_id="")

    result = enforcer.evaluate(ctx)

    assert result.decision == Decision.ALLOW
    assert ctx.tenant_id == "acme-corp"


def test_budget_overrun_is_denied():
    enforcer = GovernanceEnforcer(GovernanceConfig(enabled=True, registry_file=str(REGISTRY), default_tenant="acme-corp"))
    result = enforcer.evaluate(_ctx(cost_estimate_usd=99.0))

    assert result.decision == Decision.DENY
    assert result.rule_hits == ["GOV-BUDGET-EXCEEDED"]


def test_pipeline_governance_denial_writes_audit_and_skips_executor(tmp_path):
    calls = []
    gate6 = Gate6Audit(GateConfig(options={"audit_dir": str(tmp_path)}))
    pipeline = Pipeline(
        gate1=_AllowGate("gate1"),
        gate2=_AllowGate("gate2"),
        gate3=_AllowGate("gate3"),
        gate4=_AllowGate("gate4"),
        gate5=_AllowGate("gate5"),
        gate6=gate6,
        governance=GovernanceEnforcer(
            GovernanceConfig(enabled=True, registry_file=str(REGISTRY), default_tenant="acme-corp")
        ),
    )

    async def executor(_ctx):
        calls.append(True)
        return {"ok": True}

    result = asyncio.run(pipeline.run(_ctx(data_domain="payroll", resource_owner="all"), executor))

    assert result.allowed is False
    assert result.final_decision == Decision.DENY
    assert calls == []
    record = json.loads((tmp_path / "audit.jsonl").read_text(encoding="utf-8"))
    assert record["gen_ai.governance.human_principal"] == "bob.dev@acme.local"
    assert record["gen_ai.governance.agent_id"] == "general-office-agent"
    assert record["gen_ai.governance.data_domain"] == "payroll"
    assert "GOV-EMPLOYEE-DATA-DOMAIN" in record["gen_ai.policy.hit_id"]


def test_gate3_predicate_can_read_governance_fields(tmp_path):
    policy = tmp_path / "policy.yaml"
    policy.write_text(
        """
rules:
  - id: principal-domain-rule
    name: Principal domain rule
    source: governance-test
    triggers: [echo]
    predicate: "principal == 'bob.dev@acme.local' and data_domain == 'payroll'"
    enforce: deny
    severity: high
    audit: required
""",
        encoding="utf-8",
    )
    gate = Gate3Policy(GateConfig(options={"backend": "python", "policy_file": str(policy)}))
    result = gate.evaluate(_ctx(data_domain="payroll"))

    assert result.decision == Decision.DENY
    assert result.rule_hits == ["principal-domain-rule"]
