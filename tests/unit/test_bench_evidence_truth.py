from __future__ import annotations

import argparse
import json

from bench.cli import _cmd_report, _results_to_json
from bench.metrics import compute
from xa_guard.types import BenchCase, BenchResult, Decision, TaintLabel


def _result(
    case_id: str,
    expected: Decision,
    actual: Decision,
    *,
    audit_written: bool = True,
    audit_completeness: float = 1.0,
    infra_error: bool = False,
    note: str = "",
) -> BenchResult:
    result = BenchResult(
        case=BenchCase(
            case_id=case_id,
            dimension="data_safety",
            attack_type="benign" if expected == Decision.ALLOW else "attack",
            input_payload={},
            expected_decision=expected,
            note="case note",
        ),
        actual_decision=actual,
        actual_taint=TaintLabel.PUBLIC,
        rule_hits=["RULE-1"],
        latency_ms=1.25,
        passed=actual == expected and not infra_error,
        note=note,
        audit_written=audit_written,
        audit_complete=audit_completeness >= 1.0,
        audit_completeness=audit_completeness,
    )
    result.trace_id = f"trace-{case_id}"
    result.audit_record_hash = f"hash-{case_id}"
    result.infra_error = infra_error
    return result


def test_audit_completeness_uses_every_result_as_denominator() -> None:
    results = [
        _result("audited", Decision.DENY, Decision.DENY),
        _result(
            "missing-audit",
            Decision.ALLOW,
            Decision.ALLOW,
            audit_written=False,
            audit_completeness=0.0,
        ),
    ]

    assert compute(results).audit_completeness == 0.5


def test_infra_errors_are_reported_and_excluded_from_normal_metric_denominators() -> None:
    results = [
        _result("attack-ok", Decision.DENY, Decision.DENY),
        _result("benign-ok", Decision.ALLOW, Decision.ALLOW),
        _result(
            "attack-infra",
            Decision.DENY,
            Decision.ALLOW,
            infra_error=True,
        ),
        _result(
            "benign-infra",
            Decision.ALLOW,
            Decision.DENY,
            infra_error=True,
        ),
    ]

    metrics = compute(results)

    assert metrics.infra_errors == 2
    assert metrics.asr == 0.0
    assert metrics.recall == 1.0
    assert metrics.fpr == 0.0
    assert metrics.cup == 1.0
    assert metrics.by_dimension["data_safety"]["infra_errors"] == 2
    assert metrics.by_dimension["data_safety"]["asr"] == 0.0
    assert metrics.by_dimension["data_safety"]["fpr"] == 0.0
    assert metrics.by_dimension["data_safety"]["cup"] == 1.0


def test_results_json_preserves_evidence_infra_error_and_result_note() -> None:
    result = _result(
        "evidence",
        Decision.DENY,
        Decision.DENY,
        audit_completeness=0.75,
        infra_error=True,
        note="result note",
    )

    [item] = _results_to_json([result])

    assert item["trace_id"] == "trace-evidence"
    assert item["audit_record_hash"] == "hash-evidence"
    assert item["audit_written"] is True
    assert item["audit_completeness"] == 0.75
    assert item["infra_error"] is True
    assert item["note"] == "result note"


def test_cli_report_reconstruction_preserves_evidence_and_result_note(
    tmp_path, monkeypatch
) -> None:
    raw = _results_to_json(
        [
            _result(
                "round-trip",
                Decision.DENY,
                Decision.DENY,
                audit_completeness=0.625,
                infra_error=True,
                note="result note",
            )
        ]
    )
    results_path = tmp_path / "results.json"
    results_path.write_text(json.dumps(raw), encoding="utf-8")
    captured: dict[str, object] = {}

    def capture_render(results, metrics, *, out_path):
        captured["results"] = results
        captured["metrics"] = metrics
        return "<html></html>"

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("bench.reporters.html_report.render_html", capture_render)

    exit_code = _cmd_report(
        argparse.Namespace(results=str(results_path), format="html")
    )

    assert exit_code == 0
    [rebuilt] = captured["results"]
    assert rebuilt.trace_id == "trace-round-trip"
    assert rebuilt.audit_record_hash == "hash-round-trip"
    assert rebuilt.audit_written is True
    assert rebuilt.audit_completeness == 0.625
    assert rebuilt.infra_error is True
    assert rebuilt.note == "result note"
