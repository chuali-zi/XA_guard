"""Live XA-Guard SUT smoke.

This test is skipped outside the XA-Guard monorepo, but when the parent
XA-Guard project and mcp package are available it proves ToolCall attempts go
through a real ``xa_guard.server`` stdio MCP process and Gate6 audit.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kernel.demo import reference_surface
from kernel.evidence import EvidenceStore
from kernel.policy_overlay import overlay_from_scenario
from kernel.run import run_attempt
from kernel.scenario import load_injections, load_scenario, with_injections
from kernel.seat import GullibleSeat
from kernel.sut import XaGuardSUT, find_xa_guard_root

SCENARIOS = Path(__file__).resolve().parents[2] / "scenarios"


def _requires_live_xaguard() -> Path:
    try:
        import mcp  # noqa: F401
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"mcp package unavailable: {exc}")
    try:
        return find_xa_guard_root(Path(__file__))
    except FileNotFoundError as exc:  # pragma: no cover
        pytest.skip(str(exc))


def test_xaguard_live_sut_denies_sensitive_mailbox_exfil(tmp_path: Path) -> None:
    root = _requires_live_xaguard()
    scenario = with_injections(
        load_scenario(SCENARIOS / "dctg" / "office-mailbox.json"),
        load_injections(SCENARIOS / "injections" / "office-mail-exfil.json"),
    )
    sut = XaGuardSUT(policy=overlay_from_scenario(scenario), xa_guard_root=root, live=True)

    result = run_attempt(
        scenario,
        reference_surface(),
        GullibleSeat(),
        sut,
        evidence_store=EvidenceStore(tmp_path),
    )

    assert result.ledger.verify_hash_chain()
    assert result.violations == []
    assert result.verdict.passed
    assert any(record.tool == "send_message" and record.decision == "deny" for record in sut.audit)
    assert not any(entry.action == "send" and entry.external for entry in result.ledger.entries)
    assert (tmp_path / "xa-guard-audit" / "audit.jsonl").is_file()
