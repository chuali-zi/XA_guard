from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "range_src"))

from enterprise_agent_range.fixtures import validate_manifest


class ManifestValidationTest(unittest.TestCase):
    def test_unknown_expected_field_is_error(self) -> None:
        manifest = {
            "schema_version": "enterprise-agent-range/cases/v0.1",
            "metadata": {"suite_id": "unit"},
            "fixtures": [],
            "cases": [
                {
                    "case_id": "EAR-T-UNKNOWN",
                    "title": "unknown expected",
                    "case_kind": "benign_control",
                    "taxonomy": ["BENIGN"],
                    "domain": "office",
                    "surface": "null_adapter",
                    "principal": {"principal_id": "alice.employee@range.local"},
                    "agent": {"agent_id": "office-agent"},
                    "input": {"task": "noop", "fixture_refs": []},
                    "expected": {"decision": "allow", "not_a_real_oracle": True},
                    "safety": {"side_effects_allowed": False, "sinks": []},
                    "evidence_requirements": ["case_result"],
                    "execution": {"steps": [{"tool": "get_cpu", "args": {}}]},
                }
            ],
        }

        validation = validate_manifest(manifest, Path.cwd())

        self.assertFalse(validation.ok)
        self.assertTrue(any("unsupported expected fields" in error for error in validation.errors))

    def test_descriptive_oracle_requires_machine_oracle(self) -> None:
        manifest = {
            "schema_version": "enterprise-agent-range/cases/v0.1",
            "metadata": {"suite_id": "unit"},
            "fixtures": [],
            "cases": [
                {
                    "case_id": "EAR-T-ORACLE",
                    "title": "descriptive only",
                    "case_kind": "assurance_check",
                    "taxonomy": ["assurance"],
                    "domain": "audit",
                    "surface": "null_adapter",
                    "principal": {"principal_id": "auditor.one@range.local"},
                    "agent": {"agent_id": "audit-agent"},
                    "input": {"task": "noop", "fixture_refs": []},
                    "expected": {"oracle": "human text only"},
                    "safety": {"side_effects_allowed": False, "sinks": []},
                    "evidence_requirements": ["case_result"],
                    "execution": {"steps": [{"tool": "list_traces", "args": {}}]},
                }
            ],
        }

        validation = validate_manifest(manifest, Path.cwd())

        self.assertFalse(validation.ok)
        self.assertTrue(any("machine-checkable" in error for error in validation.errors))


if __name__ == "__main__":
    unittest.main()
