from __future__ import annotations

import json
import subprocess
from pathlib import Path

from bench.external.normalizers.agentdojo import normalize_agentdojo
from bench.external.normalizers.base import read_records
from bench.external.normalizers.injecagent import normalize_injecagent
from bench.external.provenance import file_sha256
from bench.external.schema import validate_record


def test_agentdojo_normalizer_marks_non_official():
    source = Path("bench/external/fixtures/agentdojo_smoke.jsonl")
    raw = read_records(source)[0]
    record = normalize_agentdojo(raw, input_sha256=file_sha256(source), index=0)

    assert record["benchmark"]["name"] == "agentdojo"
    assert record["benchmark"]["official_claim"] is False
    assert "not_official_reproduction" in record["limitations"]
    assert validate_record(record) == []


def test_injecagent_normalizer_marks_non_official():
    source = Path("bench/external/fixtures/injecagent_smoke.jsonl")
    raw = read_records(source)[0]
    record = normalize_injecagent(raw, input_sha256=file_sha256(source), index=0)

    assert record["benchmark"]["name"] == "injecagent"
    assert record["observed"]["attack_success"] is False
    assert record["metrics"]["asr_total"] is None
    assert record["benchmark"]["official_claim"] is False
    assert validate_record(record) == []


def test_external_normalizers_preserve_false_aliases_and_attack_attempt_label():
    agentdojo = normalize_agentdojo(
        {"id": "a", "target_success": False, "utility_success": False},
        input_sha256="a" * 64,
        index=0,
    )
    injecagent = normalize_injecagent(
        {
            "id": "i",
            "asr_valid": False,
            "task_success": False,
            "attack_attempted": False,
        },
        input_sha256="b" * 64,
        index=0,
    )

    assert agentdojo["observed"]["attack_success"] is False
    assert agentdojo["observed"]["benign_success"] is False
    assert injecagent["observed"]["attack_success"] is False
    assert injecagent["observed"]["benign_success"] is False
    assert injecagent["metrics"]["asr_total"] is False


def test_external_cli_normalize_validate_and_smoke_metrics(tmp_path: Path):
    output = tmp_path / "agentdojo-normalized.jsonl"
    normalize = subprocess.run(
        [
            "python",
            "-m",
            "bench.external.cli",
            "normalize",
            "--benchmark",
            "agentdojo",
            "--input",
            "bench/external/fixtures/agentdojo_smoke.jsonl",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(normalize.stdout)["records_written"] == 2

    validate = subprocess.run(
        ["python", "-m", "bench.external.cli", "validate", "--input", str(output)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(validate.stdout)["errors"] == []

    metrics = subprocess.run(
        ["python", "-m", "bench.external.cli", "smoke-metrics", "--input", str(output)],
        capture_output=True,
        text=True,
        check=True,
    )
    observed = json.loads(metrics.stdout)
    assert observed["records_total"] == 2
    assert observed["official_claim"] is False
    assert "not_official_benchmark_score" in observed["notes"]


def test_external_cli_archive_writes_evidence_bundle(tmp_path: Path):
    out_dir = tmp_path / "agentdojo-archive"
    archive = subprocess.run(
        [
            "python",
            "-m",
            "bench.external.cli",
            "archive",
            "--benchmark",
            "agentdojo",
            "--input",
            "bench/external/fixtures/agentdojo_smoke.jsonl",
            "--out-dir",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    assert json.loads(archive.stdout)["official_claim"] is False
    expected = {
        "manifest.json",
        "normalized.jsonl",
        "validation.json",
        "smoke-metrics.json",
        "report.json",
        "README.md",
    }
    assert expected == {path.name for path in out_dir.iterdir()}

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["benchmark"] == "agentdojo"
    assert manifest["official_claim"] is False
    assert "not_official_reproduction" in manifest["limitations"]
    assert manifest["input"]["sha256"] == file_sha256("bench/external/fixtures/agentdojo_smoke.jsonl")
    assert manifest["normalized"]["sha256"] == file_sha256(out_dir / "normalized.jsonl")
    assert manifest["schema"]["sha256"] == file_sha256("bench/schema/external-benchmark-result.schema.json")
    assert manifest["validation"]["errors"] == 0
    assert manifest["validation"]["records_total"] == 2


def test_external_cli_archive_supports_injecagent(tmp_path: Path):
    out_dir = tmp_path / "injecagent-archive"
    subprocess.run(
        [
            "python",
            "-m",
            "bench.external.cli",
            "archive",
            "--benchmark",
            "injecagent",
            "--input",
            "bench/external/fixtures/injecagent_smoke.jsonl",
            "--out-dir",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    metrics = json.loads((out_dir / "smoke-metrics.json").read_text(encoding="utf-8"))
    assert manifest["benchmark"] == "injecagent"
    assert manifest["official_claim"] is False
    assert metrics["official_claim"] is False
    assert metrics["records_total"] == manifest["normalized"]["records_total"]


def test_external_cli_archive_run_projection_is_local_evidence_only(tmp_path: Path):
    out_dir = tmp_path / "agentdojo-projection-archive"
    subprocess.run(
        [
            "python",
            "-m",
            "bench.external.cli",
            "archive",
            "--benchmark",
            "agentdojo",
            "--input",
            "bench/external/fixtures/agentdojo_smoke.jsonl",
            "--out-dir",
            str(out_dir),
            "--run-projection",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    projection_dir = out_dir / "xa-guard-projection"
    results_path = projection_dir / "results.json"
    summary_path = projection_dir / "summary.json"
    audit_verify_path = projection_dir / "audit-verify.json"
    audit_path = projection_dir / "audit" / "audit.jsonl"

    assert manifest["official_claim"] is False
    assert manifest["projection"]["enabled"] is True
    assert manifest["projection"]["claim_scope"] == "xa_guard_local_projection_only"
    assert manifest["projection"]["not_official_benchmark_score"] is True
    assert manifest["projection"]["sha256"] == file_sha256(results_path)
    assert manifest["projection"]["summary_sha256"] == file_sha256(summary_path)
    assert manifest["projection"]["audit_sha256"] == file_sha256(audit_path)
    assert manifest["projection"]["audit_verify"]["ok"] is True
    assert manifest["projection"]["audit_verify"]["record_count"] == manifest["projection"]["records_total"]
    assert manifest["projection"]["audit_verify"]["first_record_hash"]
    assert manifest["projection"]["audit_verify"]["last_record_hash"]
    assert audit_path.exists()
    assert audit_verify_path.exists()
    assert not (tmp_path / "logs" / "audit" / "audit.jsonl").exists()

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["official_claim"] is False
    assert summary["not_comparable_to_agentdojo_or_injecagent_leaderboard"] is True
    forbidden = {"asr", "score", "official_score", "leaderboard_score"}
    assert forbidden.isdisjoint(summary)

    metrics = json.loads((out_dir / "smoke-metrics.json").read_text(encoding="utf-8"))
    assert "xa_guard_projection_expected_decision_match_rate" not in metrics
    results = json.loads(results_path.read_text(encoding="utf-8"))["results"]
    assert len(results) == manifest["projection"]["records_total"]
    assert all(item["audit_written"] for item in results)
