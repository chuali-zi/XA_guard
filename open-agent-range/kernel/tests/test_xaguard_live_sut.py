"""Live XA-Guard SUT smoke.

This test is skipped outside the XA-Guard monorepo, but when the parent
XA-Guard project and mcp package are available it proves ToolCall attempts go
through a real ``xa_guard.server`` stdio MCP process and Gate6 audit.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kernel import sut as sut_module
from kernel.demo import reference_surface
from kernel.evidence import EvidenceStore
from kernel.policy_overlay import overlay_from_scenario
from kernel.run import run_attempt
from kernel.scenario import load_injections, load_scenario, with_injections
from kernel.seat import GullibleSeat, ManualSeat
from kernel.sut import ToolCall, XaGuardArtifacts, XaGuardSUT, find_xa_guard_root

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


def test_xaguard_live_sut_reuses_one_session_for_attempt(tmp_path: Path, monkeypatch) -> None:
    class FakeLiveSession:
        instances: list["FakeLiveSession"] = []

        def __init__(self, *, command, env, timeout_s=60.0) -> None:
            self.command = command
            self.env = env
            self.timeout_s = timeout_s
            self.calls: list[tuple[str, dict]] = []
            self.started = False
            self.closed = False
            FakeLiveSession.instances.append(self)

        def start(self) -> None:
            self.started = True

        def call_tool(self, tool: str, arguments: dict) -> str:
            self.calls.append((tool, arguments))
            return "fake xa-guard live allowed tool call"

        def close(self) -> None:
            self.closed = True

    monkeypatch.setattr(sut_module, "_XaGuardLiveSession", FakeLiveSession)
    scenario = load_scenario(SCENARIOS / "dctg" / "office-mailbox.json")
    sut = XaGuardSUT(xa_guard_root=tmp_path, live=True)
    audit_dir = tmp_path / "xa-guard-audit"
    audit_dir.mkdir()
    sut.artifacts = XaGuardArtifacts(
        xa_guard_yaml=tmp_path / "xa-guard.yaml",
        gate3_rules=tmp_path / "gate3-rules.yaml",
        gate4_capabilities=tmp_path / "gate4-capabilities.yaml",
        audit_dir=audit_dir,
        pending_path=tmp_path / "pending-approvals.jsonl",
        tool_schemas=tmp_path / "mcp-tool-schemas.json",
    )
    out_dir = tmp_path / "attempt"

    result = run_attempt(
        scenario,
        reference_surface(),
        ManualSeat(
            [
                ToolCall("read_record", {"record_id": "rec-002"}),
                ToolCall(
                    "send_message",
                    {"to": "甲方-政府客户", "content": "官网改版技术方案", "sources": ["rec-002"]},
                ),
            ]
        ),
        sut,
        evidence_store=EvidenceStore(out_dir),
    )

    session = FakeLiveSession.instances[0]
    summary = json.loads((out_dir / "sut-session.json").read_text(encoding="utf-8"))
    hashes = json.loads((out_dir / "artifact-hashes.json").read_text(encoding="utf-8"))

    assert result.ledger.verify_hash_chain()
    assert len(FakeLiveSession.instances) == 1
    assert session.started is True
    assert session.closed is True
    assert [tool for tool, _ in session.calls] == ["read_record", "send_message"]
    assert summary["session_scope"] == "attempt"
    assert summary["process_start_count"] == 1
    assert summary["tool_call_count"] == 2
    assert summary["closed"] is True
    assert summary["tools"] == [
        {"principal": "林工", "tool": "read_record"},
        {"principal": "林工", "tool": "send_message"},
    ]
    assert "sut-session.json" in hashes


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
