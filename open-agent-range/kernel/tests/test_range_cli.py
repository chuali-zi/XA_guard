"""Product CLI tests for day/replay/report."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

from kernel import range_cli

ROOT = Path(__file__).resolve().parents[2]
FULL_DAY = ROOT / "scenarios" / "dctg" / "full-day.json"
OFFICE_MAILBOX = ROOT / "scenarios" / "dctg" / "office-mailbox.json"


def test_day_writes_evidence_and_summary(tmp_path: Path, capsys) -> None:
    out = tmp_path / "day"

    assert (
        range_cli.main(
            [
                "day",
                "--world",
                str(FULL_DAY),
                "--agent",
                "scripted",
                "--sut",
                "null",
                "--evidence-dir",
                str(out),
            ]
        )
        == 0
    )
    summary = json.loads(capsys.readouterr().out)

    assert summary["world"] == str(FULL_DAY)
    assert summary["repeat"] == 1
    assert summary["total_violations"] == 0
    assert summary["runs"][0]["ledger_hash_chain_ok"] is True
    assert (out / "day-summary.json").is_file()
    assert (out / "ledger.jsonl").is_file()
    assert (out / "ledger-replay.json").is_file()
    assert (out / "accountability-report.json").is_file()
    assert (out / "artifact-hashes.json").is_file()


def test_day_repeat_writes_numbered_attempts(tmp_path: Path, capsys) -> None:
    out = tmp_path / "day-repeat"

    assert (
        range_cli.main(
            [
                "day",
                "--world",
                str(FULL_DAY),
                "--repeat",
                "2",
                "--evidence-dir",
                str(out),
            ]
        )
        == 0
    )
    summary = json.loads(capsys.readouterr().out)

    assert summary["repeat"] == 2
    assert (out / "run-001" / "verdict.json").is_file()
    assert (out / "run-002" / "verdict.json").is_file()
    assert summary["runs"][0]["attempt_dir"].endswith("run-001")
    assert summary["runs"][1]["attempt_dir"].endswith("run-002")


def test_day_opencode_multiround_repeat_writes_product_evidence(tmp_path: Path, capsys) -> None:
    out = tmp_path / "opencode-day"
    payload = {
        "actions": [
            {"tool": "read_record", "args": {"record_id": "rec-002"}},
            {"tool": "write_draft", "args": {"text": "方案：官网改版技术方案"}},
        ]
    }
    completed = mock.Mock(returncode=0, stdout=json.dumps(payload, ensure_ascii=False), stderr="")

    with mock.patch("kernel.seat.shutil.which", return_value="opencode.cmd"), mock.patch(
        "kernel.seat.subprocess.run", return_value=completed
    ) as fake_run:
        assert (
            range_cli.main(
                [
                    "day",
                    "--world",
                    str(OFFICE_MAILBOX),
                    "--agent",
                    "opencode",
                    "--opencode-multiround",
                    "--model",
                    "test/model",
                    "--sut",
                    "null",
                    "--repeat",
                    "3",
                    "--evidence-dir",
                    str(out),
                ]
            )
            == 0
        )
    summary = json.loads(capsys.readouterr().out)

    assert summary["agent"] == "opencode"
    assert summary["opencode_multiround"] is True
    assert summary["repeat"] == 3
    assert summary["total_violations"] == 0
    assert fake_run.call_count == 3
    for run in summary["runs"]:
        run_dir = Path(run["attempt_dir"])
        manifest = json.loads((run_dir / "run-manifest.json").read_text(encoding="utf-8"))
        tools = [json.loads(line)["tool"] for line in (run_dir / "tool-events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert run["tool_attempt_count"] == 3
        assert run["ledger_hash_chain_ok"] is True
        assert manifest["seat_id"] == "opencode"
        assert manifest["opencode_multiround"] is True
        assert tools == ["read_mail", "read_record", "write_draft"]
        assert (run_dir / "opencode-events.jsonl").is_file()


def test_replay_verifies_hashes_ledger_and_sut_audit(tmp_path: Path, capsys) -> None:
    out = tmp_path / "day"
    assert range_cli.main(["day", "--world", str(FULL_DAY), "--evidence-dir", str(out)]) == 0
    capsys.readouterr()

    assert (
        range_cli.main(
            [
                "replay",
                "--attempt",
                str(out),
                "--verify-hashes",
                "--verify-ledger",
                "--verify-sut-audit",
                "--json",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)

    assert result["ok"] is True
    assert result["checks"]["artifact_hashes"]["ok"] is True
    assert result["checks"]["ledger"]["hash_chain_ok"] is True
    assert result["checks"]["ledger"]["projection_matches_artifact"] is True
    assert result["checks"]["sut_audit"]["ok"] is True


def test_day_rerun_same_dir_keeps_artifact_hashes_replayable(tmp_path: Path, capsys) -> None:
    out = tmp_path / "day"
    assert range_cli.main(["day", "--world", str(FULL_DAY), "--evidence-dir", str(out)]) == 0
    capsys.readouterr()
    assert range_cli.main(["day", "--world", str(FULL_DAY), "--evidence-dir", str(out)]) == 0
    capsys.readouterr()

    assert (
        range_cli.main(
            [
                "replay",
                "--attempt",
                str(out),
                "--verify-hashes",
                "--verify-ledger",
                "--verify-sut-audit",
                "--json",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)

    assert result["ok"] is True
    assert result["checks"]["artifact_hashes"]["ok"] is True


def test_report_renders_json_markdown_and_html(tmp_path: Path, capsys) -> None:
    out = tmp_path / "day"
    assert range_cli.main(["day", "--world", str(FULL_DAY), "--evidence-dir", str(out)]) == 0
    capsys.readouterr()

    assert range_cli.main(["report", "--run", str(out), "--format", "json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["scenario_id"] == "dctg-full-day-six-domain"
    assert data["verdict_passed"] is True
    assert data["ledger_hash_chain_ok"] is True

    assert range_cli.main(["report", "--run", str(out), "--format", "md"]) == 0
    markdown = capsys.readouterr().out
    assert "# Open Agent Range Report" in markdown
    assert "dctg-full-day-six-domain" in markdown

    html_out = tmp_path / "report.html"
    assert range_cli.main(["report", "--run", str(out), "--format", "html", "--out", str(html_out)]) == 0
    html = html_out.read_text(encoding="utf-8")
    assert "<h1>Open Agent Range Report</h1>" in html
    assert "dctg-full-day-six-domain" in html


def test_workbench_serve_writes_static_dashboard(tmp_path: Path, capsys) -> None:
    out = tmp_path / "workbench"

    assert (
        range_cli.main(
            [
                "workbench",
                "serve",
                "--world",
                str(FULL_DAY),
                "--out-dir",
                str(out),
                "--no-server",
                "--json",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    state = json.loads((out / "workbench-state.json").read_text(encoding="utf-8"))
    html = (out / "index.html").read_text(encoding="utf-8")

    assert result["ok"] is True
    assert state["scenario_id"] == "dctg-full-day-six-domain"
    assert Path(state["world_path"]).is_absolute()
    assert Path(state["findings_dir"]).is_absolute()
    assert Path(state["dashboard_dir"]).is_absolute()
    assert "mailbox:林工@dctg.local" in state["open_surfaces"]
    assert any(tool["name"] == "send_message" and "input_schema" in tool for tool in state["tools"])
    assert state["commands"]["run_ab"].startswith("python -m kernel.range_cli run-ab")
    assert "Open Agent Range Workbench" in html
    assert "Bound Properties" in html
    assert "Manual Session Builder" in html
    assert "data-app=\"range-workbench\"" in html
    assert "commandOutput" in html
    assert "RANGE_STATE" in html
    assert "manual-session --world" in html
    assert "Run local API" in html
    assert "/api/manual-session" in html


def test_sut_check_reports_offline_configuration(capsys) -> None:
    assert (
        range_cli.main(
            [
                "sut",
                "check",
                "--sut",
                "xaguard",
                "--world",
                str(FULL_DAY),
                "--json",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)

    assert result["ok"] is True
    assert result["sut"] == "xaguard"
    assert result["scenario_id"] == "dctg-full-day-six-domain"
    assert result["smoke"]["mode"] == "offline-config"
    assert "send_message" in result["smoke"]["surface_tools"]


def test_workbench_command_aliases_are_exposed_from_range_cli(tmp_path: Path, capsys) -> None:
    finding = tmp_path / "finding.json"
    assert (
        range_cli.main(
            [
                "init-finding",
                "--world",
                str(FULL_DAY),
                "--target",
                "mailbox:林工@dctg.local",
                "--payload",
                "synthetic",
                "--task-prompt",
                "normal task",
                "--out",
                str(finding),
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert range_cli.main(["run-ab", "--finding", str(finding), "--dry-run"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["dry_run"] is True
    assert plan["plan"]["finding_id"]


def test_manual_session_alias_accepts_calls_file(tmp_path: Path, capsys) -> None:
    calls_file = tmp_path / "calls.json"
    calls_file.write_bytes(
        b"\xef\xbb\xbf"
        + json.dumps(
            [
                {"tool": "read_record", "args": {"record_id": "rec-002"}},
                {
                    "tool": "send_message",
                    "args": {"to": "甲方-政府客户", "content": "官网改版技术方案", "sources": ["rec-002"]},
                },
            ],
            ensure_ascii=False,
        ).encode("utf-8")
    )
    out = tmp_path / "manual-session"

    assert (
        range_cli.main(
            [
                "manual-session",
                "--world",
                str(OFFICE_MAILBOX),
                "--principal",
                "林工",
                "--calls-file",
                str(calls_file),
                "--sut-mode",
                "guard",
                "--out-dir",
                str(out),
                "--json",
            ]
        )
        == 0
    )
    summary = json.loads(capsys.readouterr().out)

    assert summary["call_count"] == 2
    assert summary["tools"] == ["read_record", "send_message"]
    assert summary["attempt"]["external_send_count"] == 1
    assert summary["attempt"]["sut_decisions"]["allow"] == 2
    assert summary["attempt"]["ledger_hash_chain_ok"] is True
    assert (out / "summary.json").is_file()


def test_workbench_api_manual_session_executes_and_writes_evidence(tmp_path: Path) -> None:
    state = range_cli.build_workbench_state(OFFICE_MAILBOX, tmp_path / "findings", tmp_path / "dashboard")
    result = range_cli.run_workbench_api_action(
        state,
        "manual-session",
        {
            "principal": "林工",
            "sut_mode": "guard",
            "calls": [
                {"tool": "read_record", "args": {"record_id": "rec-002"}},
                {
                    "tool": "send_message",
                    "args": {"to": "甲方-政府客户", "content": "官网改版技术方案", "sources": ["rec-002"]},
                },
            ],
        },
        api_root=tmp_path / "api-runs",
    )

    attempt_dir = Path(result["attempt_dir"])
    assert result["ok"] is True
    assert result["summary"]["call_count"] == 2
    assert result["summary"]["attempt"]["external_send_count"] == 1
    assert result["summary"]["attempt"]["ledger_hash_chain_ok"] is True
    assert (attempt_dir / "summary.json").is_file()
    assert (attempt_dir / "tool-events.jsonl").is_file()
