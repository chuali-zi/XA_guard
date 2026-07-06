"""EvidenceStore 与 run_attempt 集成测试。"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from kernel.demo import reference_scenario, reference_surface, scripted_plan
from kernel.evidence import HASH_MANIFEST
from kernel.run import run_attempt
from kernel.seat import ScriptedSeat
from kernel.sut import NullSUT
from kernel.evidence import EvidenceStore


def test_run_attempt_writes_evidence_artifacts() -> None:
    scenario = reference_scenario()
    with tempfile.TemporaryDirectory() as d:
        store = EvidenceStore(d)
        result = run_attempt(
            scenario,
            reference_surface(),
            ScriptedSeat(scripted_plan()),
            NullSUT(),
            evidence_store=store,
            evidence_meta={"kind": "baseline"},
        )
        assert result.verdict.passed
        root = Path(d)
        assert (root / "world-in.json").is_file()
        assert (root / "world-out.json").is_file()
        assert (root / "world-diff.json").is_file()
        assert (root / "timeline.jsonl").is_file()
        assert (root / "ledger.jsonl").is_file()
        assert (root / "ledger-replay.json").is_file()
        assert (root / "accountability-report.json").is_file()
        assert (root / "verdict.json").is_file()
        assert (root / "tool-events.jsonl").is_file()
        assert (root / HASH_MANIFEST).is_file()
        world_in = json.loads((root / "world-in.json").read_text(encoding="utf-8"))
        world_out = json.loads((root / "world-out.json").read_text(encoding="utf-8"))
        world_diff = json.loads((root / "world-diff.json").read_text(encoding="utf-8"))
        assert world_in["side_effects"] == []
        assert world_out["side_effects"]
        assert "side_effects" in world_diff["changed_paths"]
        replay = json.loads((root / "ledger-replay.json").read_text(encoding="utf-8"))
        assert replay["entry_count"] == len(result.ledger.entries)
        assert replay["hash_chain_ok"] is True
        assert replay["deterministic_world_replay"] == "ledger_projection_v1"
        assert replay["actions"]["send"] == 1
        assert replay["egress"][0]["data_ref"] == "rec-002"
        report = json.loads((root / "accountability-report.json").read_text(encoding="utf-8"))
        assert report["violation_count"] == 0
        manifest = json.loads((root / "run-manifest.json").read_text(encoding="utf-8"))
        assert manifest["scenario_id"] == scenario.scenario_id
        assert manifest["kind"] == "baseline"
        hashes = json.loads((root / HASH_MANIFEST).read_text(encoding="utf-8"))
        assert "ledger.jsonl" in hashes
        assert "world-out.json" in hashes
        assert "timeline.jsonl" in hashes
        assert "accountability-report.json" in hashes
        assert "verdict.json" in hashes
