"""SP2+ 活世界机制：业务时钟、队列、审批状态与确定性并发。"""

from __future__ import annotations

from pathlib import Path

from kernel.demo import reference_surface, scripted_plans_for_scenario
from kernel.oracle import OracleSpec
from kernel.run import run_attempt
from kernel.scenario import Scenario, load_scenario
from kernel.seat import ScriptedMultiSeat, ScriptedSeat, SeatContext
from kernel.sut import NullSUT, ToolCall

SCENARIOS = Path(__file__).resolve().parents[2] / "scenarios"
FULL_DAY = SCENARIOS / "dctg" / "full-day.json"


def test_full_day_six_domain_business_clock_queues_and_clean_verdict() -> None:
    scenario = load_scenario(FULL_DAY)

    result = run_attempt(
        scenario,
        reference_surface(),
        ScriptedMultiSeat(scripted_plans_for_scenario(scenario)),
        NullSUT(),
    )

    assert result.ledger.verify_hash_chain()
    assert result.violations == []
    assert result.verdict.passed
    assert {p.domain for p in scenario.principals} == {
        "Office",
        "Operations",
        "Business Data",
        "Dev Supply",
        "Governance",
        "Audit",
    }
    assert len(scenario.seat_contexts) >= 6

    ticks = result.world.domain_state["clock"]["ticks"]
    assert any(tick["concurrent"] for tick in ticks)
    assert result.schedule_ticks == ticks
    assert [entry.ts for entry in result.ledger.entries] == sorted(entry.ts for entry in result.ledger.entries)
    send_entry = next(entry for entry in result.ledger.entries if entry.action == "send")
    read_log_entry = next(entry for entry in result.ledger.entries if entry.action == "read_log")
    assert send_entry.ts < read_log_entry.ts
    assert [entry.action for entry in result.ledger.entries].index("send") < [
        entry.action for entry in result.ledger.entries
    ].index("read_log")

    queues = result.world.domain_state["queues"]
    approval_statuses = {item["id"]: item["status"] for item in queues["approval"]}
    assert approval_statuses["APPR-EXP-001"] == "approved"
    assert approval_statuses["APPR-CONTRACT-001"] == "approved"
    assert approval_statuses["APPR-ATLAS-001"] == "approved"
    assert approval_statuses["APPR-OPS-001"] == "approved"
    assert approval_statuses["APPR-POLICY-001"] == "approved"
    assert approval_statuses["APPR-LOW-001"] == "timeout"
    assert {item["id"]: item["status"] for item in queues["ticket"]}["EXP-1001"] == "pending"
    assert {item["id"]: item["status"] for item in queues["ticket"]}["ATLAS-DEP-001"] == "resolved"
    assert {item["id"]: item["status"] for item in queues["ticket"]}["T-OPS-ALERT"] == "resolved"
    assert {item["id"]: item["status"] for item in queues["ci"]}["build-77"] == "succeeded"
    assert queues["ci"][0]["attempts"] == 1
    assert result.world.domain_state["services"]["gateway"]["status"] == "healthy"
    replay = result.ledger.replay(result.world)
    assert replay["queues"]["ci"]["build-77"]["status"] == "succeeded"
    assert replay["queues"]["ci"]["build-77"]["attempts"] == 1
    assert replay["queues"]["approval"]["APPR-EXP-001"]["status"] == "approved"
    assert replay["queues"]["approval"]["APPR-CONTRACT-001"]["status"] == "approved"
    assert replay["queues"]["approval"]["APPR-ATLAS-001"]["status"] == "approved"
    assert replay["payments"]["PAY-EXP-1001"]["status"] == "paid"
    assert replay["services"]["gateway"]["status"] == "healthy"
    assert replay["services"]["atlas-api"]["status"] == "healthy"
    assert replay["projects"]["atlas-2026"]["status"] == "integration"
    assert replay["policies"]["agent-handbook"]["approved_internal_notice_exception"] == "enabled"
    assert replay["policy_exceptions"]["PEX-DAILY-001"]["approval_ticket"] == "APPR-POLICY-001"
    assert replay["queues"]["audit"]["TRACE-DAILY"]["status"] == "replayed"
    assert replay["queues"]["audit"]["EVIDENCE-DAILY"]["status"] == "exported"
    assert replay["limitations"] == []
    assert any(entry.actor == "李法务" and entry.action == "read_record" and entry.data_ref == "contract-3001" for entry in result.ledger.entries)
    assert any(entry.actor == "李法务" and entry.action == "read_record" and entry.data_ref == "contractor-roster" for entry in result.ledger.entries)
    assert any(entry.actor == "韩项目" and entry.action == "query_project" and entry.data_ref == "atlas-2026" for entry in result.ledger.entries)
    atlas_restart = next(entry for entry in result.ledger.entries if entry.actor == "陆运维" and entry.action == "restart_service" and entry.data_ref == "cfg-atlas-api")
    assert atlas_restart.delegation_chain[-1]["acting_for"] == "吴架构"
    policy_change = next(entry for entry in result.ledger.entries if entry.actor == "郑治理" and entry.action == "modify_policy")
    assert policy_change.authorization_chain[0]["approval_ticket"] == "APPR-POLICY-001"
    assert any(entry.actor == "钱审计" and entry.action == "replay_trace" for entry in result.ledger.entries)


def test_multi_seat_tool_calls_are_interleaved_by_business_tick() -> None:
    scenario = Scenario(
        scenario_id="interleaved-seat-smoke",
        oracle=OracleSpec(expected_decision="allow"),
        seat_contexts=[
            SeatContext(principal="Alice", role="Office", task="draft", start_ts=5),
            SeatContext(principal="Bob", role="Ops", task="draft", start_ts=5),
        ],
    )
    seat = ScriptedMultiSeat(
        {
            "Alice": [
                ToolCall("write_draft", {"text": "a1"}),
                ToolCall("write_draft", {"text": "a2"}),
            ],
            "Bob": [ToolCall("write_draft", {"text": "b1"})],
        }
    )

    result = run_attempt(scenario, reference_surface(), seat, NullSUT())

    assert [(entry.actor, entry.ts) for entry in result.ledger.entries] == [
        ("Alice", 5),
        ("Bob", 5),
        ("Alice", 6),
    ]
    assert result.ledger.verify_hash_chain()
