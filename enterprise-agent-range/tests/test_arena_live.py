import json
import subprocess
from unittest import mock
import tempfile
import unittest
from pathlib import Path

from enterprise_agent_range.arena.live import (
    SUT_GUARD,
    SUT_NULL,
    load_challenge,
    run_live_challenge,
    office_server_command,
    write_live_gate3_policy,
    write_opencode_config,
    write_xa_guard_config,
)


class TestArenaLiveConfig(unittest.TestCase):
    def test_xa_guard_config_points_downstream_to_office_server(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            xa_root = root / "xa"
            for rel in [
                "policies/baseline/gate1_input_patterns.yaml",
                "policies/baseline/gate2_tool_risks.yaml",
                "policies/baseline/gate3_rules.yaml",
                "policies/baseline/gate4_capabilities.yaml",
            ]:
                path = xa_root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}\n", encoding="utf-8")

            command = office_server_command(
                world_path=root / "world.json",
                principal="bob.employee@range.local",
                events_out=root / "events.jsonl",
                effects_out=root / "effects.jsonl",
            )
            config = root / "xa-guard.yaml"
            write_xa_guard_config(
                path=config,
                xa_guard_root=xa_root,
                office_command=command,
                audit_dir=root / "audit",
                pending_path=root / "pending.jsonl",
                tool_capabilities_file=xa_root / "policies/baseline/gate4_capabilities.yaml",
                policy_file=xa_root / "policies/baseline/gate3_rules.yaml",
            )
            text = config.read_text(encoding="utf-8")
            self.assertNotIn("import xa_guard", text)
            self.assertIn("enterprise_agent_range.arena.mcp_office_server", text)
            self.assertIn("downstream:", text)
            self.assertIn("audit_dir:", text)

    def test_opencode_config_can_target_guard_or_null(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            office_command = ["python", "-m", "enterprise_agent_range.arena.mcp_office_server"]

            guard_path = root / "guard-opencode.json"
            guard_server = write_opencode_config(
                path=guard_path,
                sut_mode=SUT_GUARD,
                model="opencode-go/glm-5.2",
                xa_guard_root=root / "xa",
                range_root=root / "range",
                xa_guard_config=root / "xa-guard.yaml",
                office_command=office_command,
            )
            guard = json.loads(guard_path.read_text(encoding="utf-8"))
            self.assertEqual(guard_server, "office_tools")
            self.assertEqual(guard["mcp"]["office_tools"]["command"][2], "xa_guard.server")

            null_path = root / "null-opencode.json"
            null_server = write_opencode_config(
                path=null_path,
                sut_mode=SUT_NULL,
                model="opencode-go/glm-5.2",
                xa_guard_root=root / "xa",
                range_root=root / "range",
                xa_guard_config=None,
                office_command=office_command,
            )
            null = json.loads(null_path.read_text(encoding="utf-8"))
            self.assertEqual(null_server, "office_tools")
            self.assertEqual(null["mcp"]["office_tools"]["command"], office_command)

    def test_live_gate3_policy_matches_budget_body_variants(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            baseline = root / "gate3-baseline.yaml"
            baseline.write_text("metadata:\n  name: baseline\nrules: []\n", encoding="utf-8")
            generated = root / "gate3-live.yaml"

            write_live_gate3_policy(generated, baseline)

            text = generated.read_text(encoding="utf-8")
            self.assertIn("EAR-LIVE-OFFICE-BUDGET-EGRESS", text)
            self.assertIn("contains('body', 'confidential')", text)
            self.assertIn("contains('body', 'cny 860000')", text)
            self.assertIn("contains('body', '860000')", text)

    def test_null_live_attempt_writes_artifact_hash_manifest(self):
        root = Path(__file__).resolve().parents[1]
        challenge = load_challenge(root / "cases" / "arena" / "OFFICE-INJ-001.control.json")
        completed = subprocess.CompletedProcess(args=["opencode"], returncode=0, stdout="", stderr="")
        with tempfile.TemporaryDirectory() as d:
            attempt_dir = Path(d) / "attempt-001"
            with mock.patch("enterprise_agent_range.arena.live.run_opencode", return_value=completed):
                attempt = run_live_challenge(
                    challenge=challenge,
                    manifest_root=root,
                    attempt_dir=attempt_dir,
                    sut_mode=SUT_NULL,
                    xa_guard_root=root,
                    timeout_seconds=1,
                )

            artifact_hashes = json.loads((attempt_dir / "artifact-hashes.json").read_text(encoding="utf-8"))
            verdict = json.loads((attempt_dir / "verdict.json").read_text(encoding="utf-8"))

        self.assertTrue(attempt.verdict.passed)
        self.assertEqual(verdict["sut_mode"], SUT_NULL)
        self.assertIn("world-in.json", artifact_hashes)
        self.assertIn("prompt.txt", artifact_hashes)
        self.assertIn("opencode.json", artifact_hashes)
        self.assertIn("opencode-live-agent.txt", artifact_hashes)
        self.assertIn("verdict.json", artifact_hashes)

if __name__ == "__main__":
    unittest.main()
