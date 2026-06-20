from __future__ import annotations

import json
from pathlib import Path

from scripts import verify_l3_static as verifier

ROOT = Path(__file__).resolve().parents[2]


def test_all_sections_are_machine_readable_and_runtime_claims_are_explicit() -> None:
    report = verifier.build_report(ROOT)
    assert report["schema_version"] == "xa-guard-l3-static-verification/v1"
    assert report["mode"] == "static_only"
    assert report["selected_sections"] == list(verifier.SECTIONS)
    assert report["summary"]["status"] == "pass", report
    assert {item["section"] for item in report["runtime_evidence_required"]} == set(verifier.SECTIONS)
    assert all(item["status"] == "required" and item["reason"] for item in report["runtime_evidence_required"])
    json.dumps(report)


def test_section_selection_only_runs_requested_section() -> None:
    report = verifier.build_report(ROOT, "trae")
    assert report["selected_sections"] == ["trae"]
    assert list(report["sections"]) == ["trae"]
    assert {item["section"] for item in report["runtime_evidence_required"]} == {"trae"}

def test_aibom_section_checks_external_generator_contract() -> None:
    report = verifier.build_report(ROOT, "aibom")
    section = report["sections"]["aibom"]
    checks = {item["id"]: item for item in section["checks"]}

    assert section["status"] == "pass", section
    assert checks["aibom_external_generator_api"]["status"] == "pass"
    assert checks["aibom_external_cyclonedx_16_contract"]["status"] == "pass"
    assert checks["aibom_external_generator_api"]["paths"] == [
        "src/xa_guard/aibom/external_generator.py",
        "tests/unit/test_aibom_external_generator.py",
    ]
    assert checks["aibom_external_cyclonedx_16_contract"]["paths"] == [
        "src/xa_guard/aibom/external_generator.py",
        "tests/unit/test_aibom_external_generator.py",
        "docs/L3-aibom-external-generator.md",
    ]


def test_missing_assets_fail_with_nonzero_cli_exit(tmp_path: Path, capsys) -> None:
    exit_code = verifier.main(["--root", str(tmp_path), "--section", "deployment"])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code != 0
    assert payload["summary"]["status"] == "fail"
    assert payload["sections"]["deployment"]["checks"][0]["status"] == "fail"


def test_cli_stdout_and_output_are_the_same_json(tmp_path: Path, capsys) -> None:
    output = tmp_path / "static.json"
    exit_code = verifier.main(["--root", str(ROOT), "--section", "crypto", "--output", str(output)])
    stdout_report = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert json.loads(output.read_text(encoding="utf-8")) == stdout_report
