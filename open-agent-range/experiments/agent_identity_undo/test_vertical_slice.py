from __future__ import annotations

import json
from pathlib import Path

from kernel.ledger import Ledger

from experiments.agent_identity_undo.vertical_slice import run_experiment


def test_identity_undo_vertical_slice_reaches_go(tmp_path: Path) -> None:
    out = tmp_path / "evidence"
    summary = run_experiment(out)

    assert summary["conclusion"] == "GO"
    assert summary["checks"]["identity_denied_executor_count"] == 0
    assert summary["checks"]["identity_negative_cases_all_denied"] is True
    assert summary["checks"]["valid_identity_action_executed"] is True
    assert summary["checks"]["state_restored"] is True
    assert summary["checks"]["self_approval_denied"] is True
    assert summary["checks"]["compensation_trace_distinct"] is True
    assert summary["checks"]["audit_chain_ok"] is True
    assert summary["checks"]["ledger_chain_ok"] is True
    assert summary["checks"]["raw_token_absent"] is True
    assert summary["checks"]["irreversible_truthful"] is True


def test_vertical_slice_evidence_is_append_only_and_redacted(tmp_path: Path) -> None:
    out = tmp_path / "evidence"
    summary = run_experiment(out)
    audit_text = (out / "audit.jsonl").read_text(encoding="utf-8")
    effect_rows = [
        json.loads(line)
        for line in (out / "effect-events.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]

    assert "IDN-EXPERIMENT-VERIFIED" in audit_text
    assert "experiment-ed25519" in audit_text
    assert "eyJ" not in audit_text
    assert "PRIVATE KEY" not in "\n".join(path.read_text(encoding="utf-8") for path in out.iterdir())
    assert [row["event"] for row in effect_rows] == [
        "effect_recorded",
        "undo_requested",
        "undo_approval_denied",
        "compensation_started",
        "compensation_completed",
        "effect_recorded",
        "undo_manual_required",
    ]
    assert summary["traces"]["original_action"] != summary["traces"]["compensation"]


def test_vertical_slice_ledger_records_original_compensation_and_manual_boundary(tmp_path: Path) -> None:
    out = tmp_path / "evidence"
    run_experiment(out)
    ledger = Ledger.load(out / "ledger.jsonl")
    actions = [entry.action for entry in ledger.entries]

    assert ledger.verify_hash_chain()
    assert actions.count("update_registry") == 2
    assert "compensation_completed" in actions
    assert "send" in actions
    assert "undo_manual_required" in actions
