from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "bench" / "cases" / "gate3-rule-fixtures.yaml"
POLICY = ROOT / "policies" / "baseline" / "gate3_rules.yaml"
SCRIPT = ROOT / "scripts" / "validate_gate3_rule_fixtures.py"


def test_gate3_rule_fixtures_cover_every_baseline_rule_with_positive_and_negative_cases():
    fixture = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    policy = yaml.safe_load(POLICY.read_text(encoding="utf-8"))
    baseline_ids = {rule["id"] for rule in policy["rules"]}
    by_rule = {item["rule_id"]: item for item in fixture["fixtures"]}

    assert set(by_rule) == baseline_ids
    for rule_id, item in by_rule.items():
        assert item["positive"]["expected_hit"] is True, rule_id
        assert item["negative"]["expected_hit"] is False, rule_id


def test_gate3_rule_fixture_validator_strict_passes():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--strict"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    policy = yaml.safe_load(POLICY.read_text(encoding="utf-8"))
    expected_count = len(policy["rules"])
    assert f"rules={expected_count}" in result.stdout
    assert f"positive={expected_count}" in result.stdout
    assert f"negative={expected_count}" in result.stdout
