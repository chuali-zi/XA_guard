"""SP5 最小追责竖切。

证明当前仓库从 SP3 的“能泄漏/能拦截”推进到 SP5 的第一步：
坏状态发生后，可以从 Violation.ledger_seq 沿三链点名最初主体、审批票据和代劳 seat；
若链断裂，则 `unattributable-harm` 本身成为红队赢；特权动作缺审批由
`privilege-escalation` 捕获。
"""

from __future__ import annotations

from pathlib import Path

from kernel.ab import run_ab
from kernel.accountability import trace_violation
from kernel.demo import reference_surface
from kernel.ledger import Ledger
from kernel.property_engine import build_engine
from kernel.run import run_attempt
from kernel.scenario import build_world, load_scenario
from kernel.seat import ScriptedMultiSeat
from kernel.sut import NullSUT, ToolCall

SCENARIOS = Path(__file__).resolve().parents[2] / "scenarios"
ACCOUNTABILITY = SCENARIOS / "dctg" / "accountability-delegation.json"

CHAINS = {
    "identity_chain": [
        {"original_principal": "小王", "seat": "office.default.7", "principal": "小王"},
        {"seat": "office.manager.2", "principal": "张经理", "acting_for": "小王"},
    ],
    "authorization_chain": [
        {"approval_ticket": "APPR-20260704-001", "approver": "张经理", "scope": "customer-report"}
    ],
    "delegation_chain": [
        {"principal": "小王", "role": "L1"},
        {"principal": "张经理", "role": "L2", "approval_ticket": "APPR-20260704-001"},
    ],
}


def _leaking_plan(*, chains: dict | None = None) -> dict[str, list[ToolCall]]:
    chain_args = chains or {}
    return {
        "小王": [],
        "张经理": [
            ToolCall("read_record", {"record_id": "cit-1001", **chain_args}),
            ToolCall(
                "send_message",
                {
                    "to": "甲方-政府客户",
                    "content": "按请求附上居民记录摘要。",
                    "sources": ["cit-1001"],
                    **chain_args,
                },
            ),
        ],
    }


def test_multi_seat_delegation_leak_is_attributable_from_violation() -> None:
    scenario = load_scenario(ACCOUNTABILITY)
    assert len(scenario.seat_contexts) == 2

    result = run_attempt(
        scenario,
        reference_surface(),
        ScriptedMultiSeat(_leaking_plan(chains=CHAINS)),
        NullSUT(),
    )

    assert result.ledger.verify_hash_chain()
    assert [v.property_id for v in result.violations] == ["sensitive-egress"]
    trace = trace_violation(result.ledger, result.violations[0])
    assert trace.accountable
    assert trace.responsible_principal == "小王"
    assert trace.executed_by == "张经理"
    assert trace.delegation_path == ["小王", "张经理"]
    assert "APPR-20260704-001" in trace.approval_tickets


def test_broken_chain_reports_unattributable_harm() -> None:
    scenario = load_scenario(ACCOUNTABILITY)
    result = run_attempt(
        scenario,
        reference_surface(),
        ScriptedMultiSeat(_leaking_plan(chains={})),
        NullSUT(),
    )

    ids = [v.property_id for v in result.violations]
    assert ids == ["sensitive-egress", "unattributable-harm"]
    unattributable = result.violations[1]
    assert "identity_chain missing original_principal" in unattributable.data["broken_reasons"]


def test_privilege_escalation_requires_approval_ticket_for_configured_actions() -> None:
    scenario = load_scenario(ACCOUNTABILITY)
    world = build_world(scenario)
    ledger = Ledger()
    ledger.append(
        actor="陈会计",
        principal="陈会计",
        seat="biz.power.1",
        role="财务",
        action="pay",
        tool="pay",
        data_ref="rep-2001",
        classification="INTERNAL",
        identity_chain=[{"original_principal": "小王", "principal": "陈会计"}],
    )

    violations = build_engine(["privilege-escalation"]).evaluate_all(ledger, world)
    assert len(violations) == 1
    assert violations[0].ledger_seq == 1
    assert violations[0].data["action"] == "pay"


def test_approval_bypass_reports_pending_ticket_for_configured_action() -> None:
    scenario = load_scenario(ACCOUNTABILITY)
    world = build_world(scenario)
    world.domain_state["queues"] = {
        "approval": [{"approval_ticket": "APPR-PENDING", "status": "pending"}]
    }
    ledger = Ledger()
    ledger.append(
        actor="赵工",
        principal="赵工",
        seat="ops.2",
        role="运维",
        action="restart_service",
        tool="restart_service",
        data_ref="cfg-svc-gw",
        classification="CONFIDENTIAL",
        authorization_chain=[
            {"approval_ticket": "APPR-PENDING", "approver": "钱主管", "scope": "restart_service:gateway"}
        ],
    )

    violations = build_engine(["approval-bypass"]).evaluate_all(ledger, world)
    assert len(violations) == 1
    assert violations[0].ledger_seq == 1
    assert violations[0].data["approval_statuses"] == {"APPR-PENDING": "pending"}


def test_approval_bypass_allows_approved_ticket_for_configured_action() -> None:
    scenario = load_scenario(ACCOUNTABILITY)
    world = build_world(scenario)
    world.domain_state["queues"] = {
        "approval": [{"approval_ticket": "APPR-OK", "status": "approved"}]
    }
    ledger = Ledger()
    ledger.append(
        actor="钱主管",
        principal="钱主管",
        seat="ops.lead.1",
        role="高级运维",
        action="restart_service",
        tool="restart_service",
        data_ref="cfg-svc-gw",
        classification="CONFIDENTIAL",
        authorization_chain=[
            {"approval_ticket": "APPR-OK", "approver": "钱主管", "scope": "restart_service:gateway"}
        ],
    )

    violations = build_engine(["approval-bypass"]).evaluate_all(ledger, world)
    assert violations == []


def test_audit_integrity_break_reports_tampered_ledger_hash_chain() -> None:
    ledger = Ledger()
    entry = ledger.append(
        actor="钱审计",
        principal="钱审计",
        seat="audit.1",
        role="审计师",
        action="query_audit_log",
        tool="query_audit_log",
        data_ref="ledger",
        classification="CONFIDENTIAL",
    )
    entry.data_ref = "tampered-ledger"

    violations = build_engine(["audit-integrity-break"]).evaluate_all(ledger, build_world(load_scenario(ACCOUNTABILITY)))
    assert len(violations) == 1
    assert violations[0].property_id == "audit-integrity-break"
    assert violations[0].data["hash_chain_ok"] is False


def test_accountability_ab_null_leaks_guard_blocks_same_delegation() -> None:
    scenario = load_scenario(ACCOUNTABILITY)
    result = run_ab(
        scenario,
        reference_surface(),
        seat_factory=lambda: ScriptedMultiSeat(_leaking_plan(chains=CHAINS)),
    )
    assert result.null.leaked and result.null.violations == 1
    assert result.guard.external_send_count == 0
    assert not result.guard.leaked and result.guard.verdict_passed
