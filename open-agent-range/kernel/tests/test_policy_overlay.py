"""PolicyOverlay yaml 生成测试。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from kernel.policy_overlay import PolicyOverlay, overlay_from_scenario_data, write_gate3_policy
from kernel.scenario import Scenario


def test_explicit_markers_are_scenario_driven_not_hardcoded() -> None:
    overlay = PolicyOverlay(
        scenario_id="FINANCE-INJ-001",
        sensitive_markers=("Project Zephyr payroll", "wire amount 424242"),
        deny_external_tools=("send_email", "post_url"),
    )
    text = overlay.gate3_rule_yaml()
    assert "FINANCE-INJ-001" in text
    assert "send_email" in text
    assert "post_url" in text
    assert "Project Zephyr payroll" in text
    assert "wire amount 424242" in text
    assert "Atlas" not in text
    assert "860000" not in text


def test_empty_markers_produce_no_rule_block() -> None:
    text = PolicyOverlay(scenario_id="demo").gate3_rule_yaml()
    assert text == ""


def test_overlay_from_scenario_data() -> None:
    overlay = overlay_from_scenario_data(
        {
            "scenario_id": "OFFICE-001",
            "policy": {
                "sensitive_markers": ["internal roadmap token"],
                "deny_external_tools": ["send_message"],
            },
        }
    )
    text = overlay.gate3_rule_yaml()
    assert "contains('body', 'internal roadmap token')" in text
    assert "send_message" in text
    assert "enforce: deny" in text


def test_write_gate3_policy_appends_scenario_rule_to_baseline() -> None:
    overlay = PolicyOverlay(
        scenario_id="GENERIC-002",
        sensitive_markers=("customer export 17",),
        deny_external_tools=("post_url",),
    )
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        baseline = root / "baseline.yaml"
        baseline.write_text("metadata:\n  name: baseline\nrules: []\n", encoding="utf-8")
        generated = root / "generated.yaml"
        write_gate3_policy(generated, baseline, overlay)
        text = generated.read_text(encoding="utf-8")
        assert text.startswith("metadata:\n  name: baseline")
        assert "GENERIC-002" in text
        assert "post_url" in text
        assert "customer export 17" in text


def test_overlay_from_scenario_instance() -> None:
    scenario = Scenario(
        scenario_id="demo-office",
        policy={"sensitive_markers": ["居民"], "deny_external_tools": ["send"]},
    )
    from kernel.policy_overlay import overlay_from_scenario

    overlay = overlay_from_scenario(scenario)
    assert overlay.sensitive_markers == ("居民",)
    assert overlay.deny_external_tools == ("send",)
