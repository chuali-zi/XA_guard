from __future__ import annotations

import json
from pathlib import Path

from kernel.ledger import Ledger

from experiments.agent_identity_undo.round2 import run_round2


def test_round2_reaches_go(tmp_path: Path) -> None:
    out = tmp_path / "round2"
    summary = run_round2(out)

    assert summary["conclusion"] == "ROUND2-GO"
    assert summary["checks"]["http_statuses_correct"] is True
    assert summary["checks"]["negative_executor_calls"] == 0
    assert summary["checks"]["valid_http_action_executed"] is True
    assert summary["checks"]["restart_recovery_matches"] is True
    assert summary["checks"]["wrong_key_rejected"] is True
    assert summary["checks"]["db_plaintext_absent"] is True
    assert summary["checks"]["idempotent_request"] is True
    assert summary["checks"]["self_approval_denied"] is True
    assert summary["checks"]["concurrent_single_claim"] is True
    assert summary["checks"]["state_restored"] is True
    assert summary["checks"]["durable_compensated_status"] is True
    assert summary["checks"]["audit_chain_ok"] is True
    assert summary["checks"]["ledger_chain_ok"] is True
    assert summary["checks"]["effect_event_chain_ok"] is True
    assert summary["checks"]["raw_tokens_absent"] is True


def test_round2_http_denials_are_transport_level_and_zero_execution(tmp_path: Path) -> None:
    out = tmp_path / "round2"
    summary = run_round2(out)
    statuses = {
        name: result["status_code"]
        for name, result in summary["http_negative_cases"].items()
    }

    assert statuses == {
        "missing_bearer": 401,
        "bad_signature": 401,
        "identity_conflict": 403,
        "tool_scope": 403,
    }
    assert summary["checks"]["negative_executor_calls"] == 0
    assert summary["counts"]["executor_calls"] == 2


def test_round2_store_and_ledgers_are_single_winner_and_tamper_evident(tmp_path: Path) -> None:
    out = tmp_path / "round2"
    summary = run_round2(out)
    event_rows = [
        json.loads(line)
        for line in (out / "effect-events.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    ledger = Ledger.load(out / "ledger.jsonl")
    database = (out / "effects.sqlite3").read_bytes()

    assert summary["counts"]["compensation_started_events"] == 1
    assert [row["event_type"] for row in event_rows] == [
        "effect_recorded",
        "undo_requested",
        "undo_approval_denied",
        "compensation_started",
        "compensation_completed",
    ]
    assert b"platform-team-round2" not in database
    assert ledger.verify_hash_chain()
    assert [entry.action for entry in ledger.entries].count("update_registry") == 2
    assert "compensation_completed" in [entry.action for entry in ledger.entries]
