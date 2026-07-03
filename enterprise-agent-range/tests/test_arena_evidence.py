from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "range_src"))

from enterprise_agent_range.arena.evidence import AttemptPaths, EvidenceStore
from enterprise_agent_range.io_utils import sha256_file


class ArenaEvidencePathsTest(unittest.TestCase):
    def test_attempt_paths_match_live_attempt_layout(self) -> None:
        root = Path("run/case-001.case/path-a/attempt-001")

        paths = AttemptPaths.for_attempt(root)

        self.assertEqual(paths.world_in, root / "world-in.json")
        self.assertEqual(paths.prompt, root / "prompt.txt")
        self.assertEqual(paths.opencode_events, root / "opencode-events.jsonl")
        self.assertEqual(paths.opencode_stderr, root / "opencode-stderr.txt")
        self.assertEqual(paths.office_tool_events, root / "office-tool-events.jsonl")
        self.assertEqual(paths.world_effects, root / "world-effects.jsonl")
        self.assertEqual(paths.audit_events, root / "audit" / "audit.jsonl")
        self.assertEqual(paths.audit_jsonl, root / "audit.jsonl")
        self.assertEqual(paths.verdict, root / "verdict.json")
        self.assertEqual(paths.artifact_hashes, root / "artifact-hashes.json")
        self.assertEqual(paths.opencode_config, root / "opencode.json")
        self.assertEqual(paths.opencode_live_agent, root / "opencode-live-agent.txt")
        self.assertEqual(paths.xa_guard_config, root / "xa-guard.yaml")


class EvidenceStoreTest(unittest.TestCase):
    def test_store_creates_attempt_and_audit_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            attempt_dir = Path(d) / "case-001.case" / "path-a" / "attempt-001"

            store = EvidenceStore(attempt_dir)

            self.assertTrue(store.paths.root.is_dir())
            self.assertTrue(store.paths.audit_dir.is_dir())

    def test_write_and_read_evidence_formats(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = EvidenceStore(Path(d) / "attempt-001")

            store.write_json("world_in", {"mailboxes": {"alice": []}})
            store.write_text("prompt", "read mail\n")
            store.write_jsonl("opencode_events", [{"type": "start"}])
            store.append_jsonl("opencode_events", [{"type": "done", "ok": True}])

            self.assertEqual(store.read_json("world_in"), {"mailboxes": {"alice": []}})
            self.assertEqual(store.read_text("prompt"), "read mail\n")
            self.assertEqual(
                store.read_jsonl("opencode_events"),
                [{"type": "start"}, {"ok": True, "type": "done"}],
            )

    def test_finalize_artifact_hashes_for_existing_files(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = EvidenceStore(Path(d) / "attempt-001")
            store.write_json("world_in", {"case": "OFFICE-INJ-001"})
            store.write_text("prompt", "hello\n")
            store.write_jsonl("audit_events", [{"decision": "deny"}])

            manifest = store.finalize_artifact_hashes()

            self.assertEqual(
                manifest,
                {
                    "world-in.json": sha256_file(store.paths.world_in),
                    "prompt.txt": sha256_file(store.paths.prompt),
                    "audit/audit.jsonl": sha256_file(store.paths.audit_events),
                },
            )
            self.assertEqual(store.read_json("artifact_hashes"), manifest)

    def test_finalize_skips_missing_optional_files_and_manifest_self_hash(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = EvidenceStore(Path(d) / "attempt-001")
            store.write_json("verdict", {"passed": True})

            first_manifest = store.finalize_artifact_hashes()
            second_manifest = store.finalize_artifact_hashes()

            self.assertEqual(first_manifest, {"verdict.json": sha256_file(store.paths.verdict)})
            self.assertEqual(second_manifest, first_manifest)
            self.assertNotIn("artifact-hashes.json", second_manifest)
            self.assertFalse(store.paths.opencode_stderr.exists())
            self.assertNotIn("opencode-stderr.txt", second_manifest)


if __name__ == "__main__":
    unittest.main()
