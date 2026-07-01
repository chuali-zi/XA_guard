from __future__ import annotations

import asyncio
import json
from pathlib import Path

from xa_guard.config import GateConfig, GovernanceConfig
from xa_guard.gates.base import Gate, GateStage
from xa_guard.gates.gate6_audit import Gate6Audit
from xa_guard.governance import GovernanceEnforcer, GovernanceRegistry
from xa_guard.pipeline import Pipeline
from xa_guard.proxy.upstream import _ctx_with_governance
from xa_guard.types import Decision, GateContext, GateResult


REGISTRY = Path("configs/governance.enterprise-static.yaml")


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


def _enforcer(path: Path = REGISTRY) -> GovernanceEnforcer:
    return GovernanceEnforcer(GovernanceConfig(enabled=True, registry_file=str(path), default_tenant="acme-corp"))


def test_enterprise_registry_loads_v02_assets_and_schema_file():
    schema = json.loads(Path("schemas/governance-registry.schema.json").read_text(encoding="utf-8"))
    registry = GovernanceRegistry.from_yaml(REGISTRY)

    assert schema["properties"]["schema_version"]["const"] == "xa-guard-governance/v0.2"
    assert registry.schema_version == "xa-guard-governance/v0.2"
    assert registry.registry_version == "enterprise-static-2026-07-01"
    assert "hr_staff" in registry.roles
    assert registry.budgets["bob.dev@acme.local"]["limit_usd"] == 8.0
    assert round(registry.employees["bob.dev@acme.local"].remaining_budget_usd, 2) == 6.9
    assert "GOV-APPROVAL-CONFIDENTIAL-CROSS-SUBJECT" in {
        policy.policy_id for policy in registry.approval_policies
    }


def test_enterprise_rbac_allows_engineer_to_use_general_agent_for_engineering_docs():
    result = _enforcer().evaluate(_ctx())

    assert result.decision == Decision.ALLOW
    assert result.metadata["role_ids"] == ["engineer"]
    assert result.metadata["decision_reason_code"] == "GOV-ALLOW"


def test_enterprise_rbac_denies_tool_not_granted_to_role():
    result = _enforcer().evaluate(_ctx(tool_name="send_email"))

    assert result.decision == Decision.DENY
    assert result.rule_hits == ["GOV-AGENT-TOOL-SCOPE"]
    assert result.metadata["decision_reason_code"] == "GOV-AGENT-TOOL-SCOPE"


def test_enterprise_abac_denies_engineer_payroll_cross_subject_access():
    result = _enforcer().evaluate(_ctx(data_domain="payroll", resource_owner="all"))

    assert result.decision == Decision.DENY
    assert result.rule_hits == ["GOV-EMPLOYEE-DATA-DOMAIN"]


def test_enterprise_hr_cross_subject_payroll_requires_stable_approval_policy():
    result = _enforcer().evaluate(
        _ctx(
            human_principal="alice.hr@acme.local",
            agent_id="hr-assistant",
            data_domain="payroll",
            resource_owner="bob.dev@acme.local",
            cost_estimate_usd=0.30,
        )
    )

    assert result.decision == Decision.REQUIRE_APPROVAL
    assert "GOV-APPROVAL-CONFIDENTIAL-CROSS-SUBJECT" in result.rule_hits
    assert result.metadata["approval_policy_id"] == "GOV-APPROVAL-CONFIDENTIAL-CROSS-SUBJECT"
    assert result.metadata["role_ids"] == ["hr_staff"]


def test_enterprise_inactive_principal_and_agent_fail_closed():
    disabled_principal = _enforcer().evaluate(
        _ctx(
            human_principal="mallory.disabled@acme.local",
            agent_id="security-review-agent",
            data_domain="engineering_docs",
        )
    )
    disabled_agent = _enforcer().evaluate(
        _ctx(
            human_principal="bob.dev@acme.local",
            agent_id="security-review-agent",
            data_domain="engineering_docs",
        )
    )

    assert disabled_principal.decision == Decision.DENY
    assert disabled_principal.rule_hits == ["GOV-UNKNOWN-PRINCIPAL"]
    assert disabled_agent.decision == Decision.DENY
    assert disabled_agent.rule_hits == ["GOV-UNKNOWN-AGENT"]


def test_enterprise_cross_tenant_agent_or_domain_is_denied():
    beta_agent = _enforcer().evaluate(_ctx(agent_id="beta-ops-agent"))
    beta_domain = _enforcer().evaluate(_ctx(data_domain="beta_ops_notes"))

    assert beta_agent.decision == Decision.DENY
    assert beta_agent.rule_hits == ["GOV-TENANT-MISMATCH"]
    assert beta_domain.decision == Decision.DENY
    assert beta_domain.rule_hits == ["GOV-TENANT-MISMATCH"]


def test_enterprise_budget_overrun_is_denied():
    result = _enforcer().evaluate(_ctx(cost_estimate_usd=99.0))

    assert result.decision == Decision.DENY
    assert result.rule_hits == ["GOV-BUDGET-EXCEEDED"]


def test_enterprise_registry_validation_rejects_dangling_role_binding(tmp_path):
    registry = tmp_path / "bad-governance.yaml"
    registry.write_text(
        """
schema_version: xa-guard-governance/v0.2
default_tenant: acme-corp
tenants:
  - tenant_id: acme-corp
    status: active
principals: []
groups: []
roles: []
role_bindings:
  - binding_id: bad
    tenant_id: acme-corp
    role_id: missing-role
    status: active
agents: []
data_domains: []
""",
        encoding="utf-8",
    )

    try:
        GovernanceRegistry.from_yaml(registry)
    except ValueError as exc:
        assert "unknown role" in str(exc)
    else:
        raise AssertionError("dangling role binding was accepted")


def test_enterprise_envelope_accepts_principal_id_alias_and_summarizes_capability_token():
    ctx = _ctx_with_governance(
        "echo",
        {"text": "hello"},
        {
            "tenant_id": "acme-corp",
            "principal_id": "bob.dev@acme.local",
            "agent_id": "general-office-agent",
            "data_domain": "engineering_docs",
            "capability_token": {
                "scope": "engineering:read",
                "token": "raw-secret-token",
                "signature": "raw-signature",
            },
        },
    )

    assert ctx.human_principal == "bob.dev@acme.local"
    assert ctx.capability_token_summary["scope"] == "engineering:read"
    assert "token_sha256" in ctx.capability_token_summary
    assert "signature_sha256" in ctx.capability_token_summary
    assert "raw-secret-token" not in json.dumps(ctx.capability_token_summary)


def test_enterprise_audit_writes_governance_metadata_and_omits_raw_capability_secret(tmp_path):
    calls = []
    pipeline = Pipeline(
        gate1=_AllowGate("gate1"),
        gate2=_AllowGate("gate2"),
        gate3=_AllowGate("gate3"),
        gate4=_AllowGate("gate4"),
        gate5=_AllowGate("gate5"),
        gate6=Gate6Audit(GateConfig(options={"audit_dir": str(tmp_path)})),
        governance=_enforcer(),
    )
    ctx = _ctx_with_governance(
        "echo",
        {"text": "hello"},
        {
            "tenant_id": "acme-corp",
            "principal_id": "bob.dev@acme.local",
            "agent_id": "general-office-agent",
            "data_domain": "engineering_docs",
            "resource_owner": "bob.dev@acme.local",
            "task_id": "task-audit",
            "cost_estimate_usd": 0.20,
            "capability_token": {"scope": "engineering:read", "token": "raw-secret-token"},
        },
    )

    async def executor(_ctx):
        calls.append(True)
        return {"ok": True}

    result = asyncio.run(pipeline.run(ctx, executor))
    record = json.loads((tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()[0])

    assert result.allowed is True
    assert calls == [True]
    assert record["gen_ai.governance.registry_version"] == "enterprise-static-2026-07-01"
    assert record["gen_ai.governance.policy_version"] == "xa-guard-governance/v0.2"
    assert record["gen_ai.governance.decision_reason_code"] == "GOV-ALLOW"
    assert record["gen_ai.governance.role_ids"] == ["engineer"]
    assert "token_sha256" in record["gen_ai.governance.capability_token"]
    assert "raw-secret-token" not in json.dumps(record, ensure_ascii=False)
