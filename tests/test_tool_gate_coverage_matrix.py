from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.generate_tool_gate_coverage_matrix import (
    DEFAULT_BENCH,
    build_matrix,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate_tool_gate_coverage_matrix.py"


def test_gate3_triggers_have_gate2_and_gate4_registration():
    matrix = build_matrix(bench_path=DEFAULT_BENCH)
    summary = matrix["summary"]

    assert summary["gate3_trigger_tools"] == 45
    assert summary["bench_tools"] == 24
    assert summary["missing_gate2_for_gate3"] == []
    assert summary["missing_gate4_for_gate3"] == []
    assert summary["risk_mismatches"] == []
    assert summary["invalid_risk"] == []
    assert summary["invalid_taint"] == []


def test_matrix_includes_install_plugin_in_unified_tool_ledger():
    matrix = build_matrix(bench_path=DEFAULT_BENCH)
    summary = matrix["summary"]
    by_tool = {row["tool"]: row for row in matrix["rows"]}

    assert summary["bench_only"] == []
    assert by_tool["install_plugin"]["status"] == "OK"
    assert by_tool["install_plugin"]["gate2_risk"] == "red"
    assert by_tool["install_plugin"]["gate4_risk"] == "red"
    assert by_tool["install_plugin"]["gate3_rule_count"] >= 1
    assert by_tool["install_plugin"]["bench_case_count"] == 25


def test_matrix_uses_overlay_merged_view(tmp_path):
    overlay = tmp_path / "overlay" / "acme"
    overlay.mkdir(parents=True)
    (overlay / "manifest.yaml").write_text("metadata:\n  layer: overlay\n", encoding="utf-8")
    (overlay / "policy.yaml").write_text(
        """
rules:
  - id: tenant::acme::custom-export-review
    name: Custom export review
    source: tenant
    triggers: [tenant_export]
    predicate: "tool == 'tenant_export'"
    enforce: require_approval
    severity: high
    audit: required
""",
        encoding="utf-8",
    )
    (overlay / "tool_capabilities.yaml").write_text(
        """
tools:
  - tool_name: tenant_export
    capabilities: [DATA_EXPORT]
    input_max_taint: INTERNAL
    output_taint: INTERNAL
    risk_level: yellow
""",
        encoding="utf-8",
    )
    matrix = build_matrix(overlay_root=tmp_path / "overlay", bench_path=DEFAULT_BENCH)
    by_tool = {row["tool"]: row for row in matrix["rows"]}

    assert by_tool["tenant_export"]["status"] == "NO_BENCH_CASE"
    assert by_tool["tenant_export"]["gate2_risk"] == "yellow"
    assert by_tool["tenant_export"]["gate3_rule_count"] == 1
    assert by_tool["tenant_export"]["gate4_risk"] == "yellow"


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
    assert "Bench-only tools: **0**" in text
    assert "install_plugin" in text
