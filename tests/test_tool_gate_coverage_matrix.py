from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.generate_tool_gate_coverage_matrix import (
    DEFAULT_BENCH,
    DEFAULT_GATE2,
    DEFAULT_GATE3,
    DEFAULT_GATE4,
    build_matrix,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate_tool_gate_coverage_matrix.py"


def test_gate3_triggers_have_gate2_and_gate4_registration():
    matrix = build_matrix(DEFAULT_GATE2, DEFAULT_GATE3, DEFAULT_GATE4, DEFAULT_BENCH)
    summary = matrix["summary"]

    assert summary["gate3_trigger_tools"] == 43
    assert summary["bench_tools"] == 24
    assert summary["missing_gate2_for_gate3"] == []
    assert summary["missing_gate4_for_gate3"] == []
    assert summary["risk_mismatches"] == []
    assert summary["invalid_risk"] == []
    assert summary["invalid_taint"] == []


def test_matrix_surfaces_known_bench_only_supply_chain_tool():
    matrix = build_matrix(DEFAULT_GATE2, DEFAULT_GATE3, DEFAULT_GATE4, DEFAULT_BENCH)
    summary = matrix["summary"]
    by_tool = {row["tool"]: row for row in matrix["rows"]}

    assert summary["bench_only"] == ["install_plugin"]
    assert by_tool["install_plugin"]["status"] == "BENCH_ONLY"
    assert by_tool["install_plugin"]["bench_case_count"] == 25


def test_coverage_matrix_script_strict_writes_report(tmp_path):
    report = tmp_path / "matrix.md"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--strict", "--report", str(report)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    text = report.read_text(encoding="utf-8")
    assert "# Tool x Gate coverage matrix" in text
    assert "Gate3 triggers missing Gate2 registration: **0**" in text
    assert "Gate2/Gate4 risk mismatches: **0**" in text
    assert "Bench-only tools: **1**" in text
    assert "install_plugin" in text
