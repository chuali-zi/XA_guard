from __future__ import annotations

import pytest

from xa_guard.control.ceiling import CeilingError, GovernanceCeiling
from xa_guard.control.contracts import ContractError, ContractRegistry, contract_succeeded, resolve_pointer


def test_v2_ticket_contract_and_strict_missing_write_contract() -> None:
    registry = ContractRegistry(
        "policies/baseline/tool_effects.yaml",
        "policies/baseline/gate4_capabilities.yaml",
    )
    contract = registry.for_tool("business_submit_ticket")
    assert contract is not None
    assert contract.contract_version == "2"
    assert contract.undo_window_seconds == 3600
    assert contract_succeeded(contract, {"ok": True})
    assert not contract_succeeded(contract, {"ok": False})
    with pytest.raises(ContractError):
        registry.for_tool("send_email")


def test_contract_pointer_mapping() -> None:
    root = {"result": {"body": {"ticket_id": "TKT-1"}}}
    assert resolve_pointer(root, "$result#/body/ticket_id") == "TKT-1"
    with pytest.raises(ContractError):
        resolve_pointer(root, "$result#/body/missing")


def test_assignment_must_stay_inside_static_agent_ceiling() -> None:
    ceiling = GovernanceCeiling("configs/governance.enterprise-static.yaml")
    accepted = {
        "subject_type": "group",
        "subject_id": "engineering-team",
        "agent_id": "general-office-agent",
        "tools": ["business_submit_ticket"],
        "data_domains": ["engineering_docs"],
    }
    assert ceiling.validate_assignment("acme-corp", accepted).agent_id == "general-office-agent"
    with pytest.raises(CeilingError):
        ceiling.validate_assignment("acme-corp", {**accepted, "tools": ["drop_table"]})
    with pytest.raises(CeilingError):
        ceiling.validate_assignment("beta-corp", accepted)

