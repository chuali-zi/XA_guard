from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "range_src"))

from enterprise_agent_range.runner import run_cases


class RunnerSmokeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="ear-test-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_runner_writes_evidence_bundle(self) -> None:
        (self.tmp / "cases").mkdir()
        (self.tmp / "fixtures" / "policies").mkdir(parents=True)
        (self.tmp / "fixtures" / "policies" / "public-policy.md").write_text(
            "# Public Policy\n\nSynthetic public policy text.",
            encoding="utf-8",
        )
        manifest = {
            "schema_version": "enterprise-agent-range/cases/v0.1",
            "metadata": {"suite_id": "unit", "created_at": "2026-07-01", "owner": "tests"},
            "fixtures": [
                {
                    "fixture_id": "public-policy",
                    "kind": "policy_doc",
                    "path": "fixtures/policies/public-policy.md",
                    "classification": "PUBLIC",
                    "contains_attack": False,
                    "synthetic": True,
                    "sha256": "pending",
                }
            ],
            "manual_findings": [],
            "chains": [],
            "cases": [
                {
                    "case_id": "EAR-T-001",
                    "title": "read public policy",
                    "case_kind": "benign_control",
                    "taxonomy": ["BENIGN"],
                    "domain": "office",
                    "surface": "null_adapter",
                    "principal": {"principal_id": "alice.employee@range.local", "role": "Employee"},
                    "agent": {"agent_id": "office-agent", "agent_type": "OfficeAgent"},
                    "input": {
                        "task": "Read public policy",
                        "fixture_refs": ["fixtures/policies/public-policy.md"],
                    },
                    "expected": {
                        "decision": "allow",
                        "downstream_call_count": 0,
                        "audit_required": True,
                        "audit_chain_valid": True,
                    },
                    "safety": {"side_effects_allowed": False, "sinks": []},
                    "evidence_requirements": ["case_result", "audit_record", "fixture_hash"],
                    "execution": {
                        "steps": [
                            {
                                "tool": "read_policy_doc",
                                "args": {"fixture_ref": "fixtures/policies/public-policy.md"},
                            }
                        ]
                    },
                },
                {
                    "case_id": "EAR-T-002",
                    "title": "read public policy again",
                    "case_kind": "benign_control",
                    "taxonomy": ["BENIGN"],
                    "domain": "office",
                    "surface": "null_adapter",
                    "principal": {"principal_id": "alice.employee@range.local", "role": "Employee"},
                    "agent": {"agent_id": "office-agent", "agent_type": "OfficeAgent"},
                    "input": {
                        "task": "Read public policy again",
                        "fixture_refs": ["fixtures/policies/public-policy.md"],
                    },
                    "expected": {
                        "decision": "allow",
                        "downstream_call_count": 0,
                        "audit_required": True,
                        "audit_chain_valid": True,
                    },
                    "safety": {"side_effects_allowed": False, "sinks": []},
                    "evidence_requirements": ["case_result", "audit_record", "fixture_hash"],
                    "execution": {
                        "steps": [
                            {
                                "tool": "read_policy_doc",
                                "args": {"fixture_ref": "fixtures/policies/public-policy.md"},
                            }
                        ]
                    },
                },
            ],
        }
        manifest_path = self.tmp / "cases" / "p0_manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        summary = run_cases(
            manifest_path=manifest_path,
            output_root=self.tmp / "reports",
            run_id="run-unit",
        )

        self.assertEqual(summary.metrics["counts"]["total_cases"], 2)
        self.assertEqual(summary.metrics["counts"]["pass"], 2)
        rows = [
            json.loads(line)
            for line in (summary.run_dir / "case-results.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        self.assertTrue(rows[1]["actual"]["audit_chain_valid"])
        self.assertTrue((summary.run_dir / "case-results.jsonl").exists())
        self.assertTrue((summary.run_dir / "artifact-hashes.json").exists())


if __name__ == "__main__":
    unittest.main()
