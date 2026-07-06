"""Product CLI tests for day/replay/report."""

from __future__ import annotations

import json
from pathlib import Path

from kernel import range_cli

ROOT = Path(__file__).resolve().parents[2]
FULL_DAY = ROOT / "scenarios" / "dctg" / "full-day.json"


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
    assert "mailbox:林工@dctg.local" in state["open_surfaces"]
    assert state["commands"]["run_ab"].startswith("python -m kernel.range_cli run-ab")
    assert "Open Agent Range Workbench" in html
    assert "Bound Properties" in html


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
