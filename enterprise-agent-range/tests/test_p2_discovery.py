from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "range_src"))

from enterprise_agent_range.p2 import discovery
from enterprise_agent_range.p2.base import CapabilityStatus


class DiscoveryScanTest(unittest.TestCase):
    def test_empty_observed_returns_empty_list(self) -> None:
        inventory = {"declared_agents": ["a1"], "declared_tools": ["t1"], "observed": []}
        self.assertEqual(discovery.DiscoveryScan().scan(inventory), [])

    def test_missing_observed_key_returns_empty_list(self) -> None:
        inventory = {"declared_agents": [], "declared_tools": []}
        self.assertEqual(discovery.DiscoveryScan().scan(inventory), [])

    def test_declared_agent_and_tool_are_ignored(self) -> None:
        inventory = {
            "declared_agents": ["a1"],
            "declared_tools": ["t1"],
            "observed": [
                {"kind": "agent", "id": "a1"},
                {"kind": "tool", "id": "t1"},
            ],
        }
        self.assertEqual(discovery.DiscoveryScan().scan(inventory), [])

    def test_undeclared_agent_becomes_high_severity_finding(self) -> None:
        inventory = {
            "declared_agents": ["a1"],
            "declared_tools": [],
            "observed": [{"kind": "agent", "id": "shadow-agent"}],
        }
        findings = discovery.DiscoveryScan().scan(inventory)
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(finding.kind, "unregistered_agent")
        self.assertEqual(finding.severity, "high")
        self.assertEqual(finding.evidence_ref, "observed:agent:shadow-agent")
        self.assertEqual(finding.finding_id, "agent:shadow-agent")

    def test_undeclared_tool_becomes_medium_severity_finding(self) -> None:
        inventory = {
            "declared_agents": [],
            "declared_tools": ["t1"],
            "observed": [{"kind": "tool", "id": "shadow-tool"}],
        }
        findings = discovery.DiscoveryScan().scan(inventory)
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(finding.kind, "unapproved_plugin")
        self.assertEqual(finding.severity, "medium")
        self.assertEqual(finding.evidence_ref, "observed:tool:shadow-tool")
        self.assertEqual(finding.finding_id, "tool:shadow-tool")

    def test_evidence_field_used_when_present(self) -> None:
        inventory = {
            "declared_agents": [],
            "declared_tools": [],
            "observed": [{"kind": "agent", "id": "a2", "evidence": "trace:fixture-42"}],
        }
        findings = discovery.DiscoveryScan().scan(inventory)
        self.assertEqual(findings[0].evidence_ref, "trace:fixture-42")

    def test_unknown_kind_is_ignored(self) -> None:
        inventory = {
            "declared_agents": [],
            "declared_tools": [],
            "observed": [{"kind": "rogue_endpoint", "id": "x1"}],
        }
        self.assertEqual(discovery.DiscoveryScan().scan(inventory), [])

    def test_mixed_declared_and_shadow_entries(self) -> None:
        inventory = {
            "declared_agents": ["a1"],
            "declared_tools": ["t1"],
            "observed": [
                {"kind": "agent", "id": "a1"},
                {"kind": "agent", "id": "a2"},
                {"kind": "tool", "id": "t1"},
                {"kind": "tool", "id": "t2"},
            ],
        }
        findings = discovery.DiscoveryScan().scan(inventory)
        finding_ids = [f.finding_id for f in findings]
        # Sorted by (kind, finding_id): "unapproved_plugin" < "unregistered_agent".
        self.assertEqual(finding_ids, ["tool:t2", "agent:a2"])

    def test_output_sorted_by_kind_then_finding_id(self) -> None:
        inventory = {
            "declared_agents": [],
            "declared_tools": [],
            "observed": [
                {"kind": "tool", "id": "zeta-tool"},
                {"kind": "agent", "id": "zeta-agent"},
                {"kind": "tool", "id": "alpha-tool"},
                {"kind": "agent", "id": "alpha-agent"},
            ],
        }
        findings = discovery.DiscoveryScan().scan(inventory)
        pairs = [(f.kind, f.finding_id) for f in findings]
        self.assertEqual(pairs, sorted(pairs))
        self.assertEqual(
            pairs,
            [
                ("unapproved_plugin", "tool:alpha-tool"),
                ("unapproved_plugin", "tool:zeta-tool"),
                ("unregistered_agent", "agent:alpha-agent"),
                ("unregistered_agent", "agent:zeta-agent"),
            ],
        )

    def test_scan_is_deterministic_across_repeated_calls(self) -> None:
        inventory = {
            "declared_agents": [],
            "declared_tools": [],
            "observed": [
                {"kind": "tool", "id": "b"},
                {"kind": "tool", "id": "a"},
                {"kind": "agent", "id": "c"},
            ],
        }
        scanner = discovery.DiscoveryScan()
        first = scanner.scan(inventory)
        second = scanner.scan(inventory)
        self.assertEqual(first, second)


class DiscoverySpecTest(unittest.TestCase):
    def test_spec_marked_implemented(self) -> None:
        self.assertEqual(discovery.SPEC.status, CapabilityStatus.IMPLEMENTED)
        self.assertEqual(discovery.SPEC.key, "discovery")
        self.assertEqual(discovery.SPEC.module, discovery.__name__)


if __name__ == "__main__":
    unittest.main()
