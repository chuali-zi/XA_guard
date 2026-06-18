from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import benchmark_l3_performance as benchmark


DECISIONS = {"allow", "warn", "deny", "require_approval"}


def _write_minimal_config(tmp_path: Path) -> Path:
    config = tmp_path / "benchmark.yaml"
    config.write_text(
        """\
xa_guard:
  gates:
    gate1: {enabled: false}
    gate2: {enabled: false}
    gate3: {enabled: false}
    gate4: {enabled: false}
    gate5: {enabled: false}
    gate6: {enabled: false}
""",
        encoding="utf-8",
    )
    return config


def _sample_report(config: Path, audit_dir: Path) -> dict:
    return {
        "schema_version": "xa-l3-performance-benchmark/v0.1",
        "generated_at": "2026-06-18T00:00:00Z",
        "config": {"path": str(config), "sha256": "abc123"},
        "workload": {
            "requests": 8,
            "warmup": 2,
            "concurrency": 4,
            "cases": ["allow", "deny", "approval"],
            "includes_gate6_audit_write": True,
        },
        "summary": {
            "throughput_qps": 100.0,
            "latency": {"p50_ms": 1.25, "p95_ms": 2.5},
            "memory": {"rss_peak_mb": 64.0},
            "decisions": {"allow": 8},
            "audit": {"path": str(audit_dir / "audit.jsonl")},
            "targets_met": True,
        },
    }


def test_run_benchmark_returns_performance_report_schema(tmp_path: Path) -> None:
    config = _write_minimal_config(tmp_path)
    audit_dir = tmp_path / "audit"

    report = benchmark.run_benchmark(
        config_path=config,
        requests=6,
        warmup=1,
        concurrency=2,
        audit_dir=audit_dir,
    )

    assert {
        "schema_version",
        "generated_at",
        "config",
        "workload",
        "summary",
    } <= report.keys()
    assert report["schema_version"] == "xa-l3-performance-benchmark/v0.1"
    assert isinstance(report["generated_at"], str) and report["generated_at"]
    assert report["config"]["path"] == str(config.resolve())
    assert report["config"]["sha256"]
    assert report["workload"]["requests"] == 6
    assert report["workload"]["warmup"] == 1
    assert report["workload"]["concurrency"] == 2

    summary = report["summary"]
    latency = summary["latency"]
    assert {"p50_ms", "p95_ms"} <= latency.keys()
    assert 0 <= latency["p50_ms"] <= latency["p95_ms"]
    assert isinstance(summary["throughput_qps"], (int, float))
    assert summary["throughput_qps"] > 0

    memory = summary["memory"]
    assert "rss_peak_mb" in memory
    assert memory["rss_peak_mb"] is None or memory["rss_peak_mb"] >= 0

    counts = summary["decisions"]
    decision_counts = {name: counts.get(name, 0) for name in DECISIONS}
    assert all(isinstance(value, int) and value >= 0 for value in counts.values())
    assert sum(decision_counts.values()) == 6

    # The public result must be directly suitable for CLI JSON emission.
    json.dumps(report)


def test_main_prints_json_report_and_returns_success(monkeypatch, tmp_path: Path, capsys) -> None:
    config = tmp_path / "config.yaml"
    audit_dir = tmp_path / "audit"
    expected = _sample_report(config, audit_dir)
    observed: dict = {}

    def fake_run_benchmark(config_path, **kwargs):
        observed["config_path"] = config_path
        observed.update(kwargs)
        return expected

    monkeypatch.setattr(benchmark, "run_benchmark", fake_run_benchmark)

    exit_code = benchmark.main(
        [
            "--config",
            str(config),
            "--requests",
            "8",
            "--warmup",
            "2",
            "--concurrency",
            "4",
            "--audit-dir",
            str(audit_dir),
            "--output",
            str(tmp_path / "report.json"),
        ]
    )

    assert exit_code == 0
    stdout = capsys.readouterr().out
    printed_summary, end = json.JSONDecoder().raw_decode(stdout)
    assert printed_summary == expected["summary"]
    assert stdout[end:].strip().startswith("report=")
    assert json.loads((tmp_path / "report.json").read_text(encoding="utf-8")) == expected
    assert observed == {
        "config_path": str(config),
        "requests": 8,
        "warmup": 2,
        "concurrency": 4,
        "audit_dir": str(audit_dir),
    }


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("--requests", "0"),
        ("--requests", "-1"),
        ("--warmup", "-1"),
        ("--concurrency", "0"),
        ("--concurrency", "-1"),
    ],
)
def test_main_rejects_invalid_numeric_arguments(option: str, value: str, capsys) -> None:
    exit_code = benchmark.main([option, value])

    assert exit_code == 2
    assert "benchmark error:" in capsys.readouterr().err
