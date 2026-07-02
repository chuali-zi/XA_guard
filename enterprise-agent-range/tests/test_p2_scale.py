from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "range_src"))

import json
import tempfile

from enterprise_agent_range.p2 import scale
from enterprise_agent_range.p2.base import CapabilityStatus


def _write_manifest(case_ids: list[str]) -> str:
    fh = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    )
    json.dump({"cases": [{"case_id": cid} for cid in case_ids]}, fh)
    fh.close()
    return fh.name


CASE_IDS = [f"P1-A-{i:03d}" for i in range(1, 21)]


class SharderPartitionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest_path = _write_manifest(CASE_IDS)

    def test_shards_form_a_true_partition(self) -> None:
        plan = scale.BatchPlan(plan_id="p1", manifest_path=self.manifest_path, shard_count=4, seed=1)
        shards = scale.Sharder().shard(plan)
        self.assertEqual(len(shards), 4)
        self.assertTrue(scale.verify_partition(plan, shards))

        all_ids: list[str] = []
        for shard in shards:
            all_ids.extend(shard.case_ids)
        self.assertEqual(sorted(all_ids), sorted(CASE_IDS))
        self.assertEqual(len(all_ids), len(set(all_ids)))

    def test_each_shard_case_ids_are_sorted(self) -> None:
        plan = scale.BatchPlan(plan_id="p1", manifest_path=self.manifest_path, shard_count=3, seed=7)
        shards = scale.Sharder().shard(plan)
        for shard in shards:
            self.assertEqual(list(shard.case_ids), sorted(shard.case_ids))

    def test_shards_ordered_by_index(self) -> None:
        plan = scale.BatchPlan(plan_id="p1", manifest_path=self.manifest_path, shard_count=5, seed=2)
        shards = scale.Sharder().shard(plan)
        self.assertEqual([shard.index for shard in shards], list(range(5)))
        for shard in shards:
            self.assertEqual(shard.plan_id, "p1")


class SharderDeterminismTest(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest_path = _write_manifest(CASE_IDS)

    def test_same_plan_yields_same_shards(self) -> None:
        plan = scale.BatchPlan(plan_id="p1", manifest_path=self.manifest_path, shard_count=6, seed=42)
        shards_a = scale.Sharder().shard(plan)
        shards_b = scale.Sharder().shard(plan)
        self.assertEqual(shards_a, shards_b)

    def test_different_seed_can_change_assignment(self) -> None:
        plan_a = scale.BatchPlan(plan_id="p1", manifest_path=self.manifest_path, shard_count=6, seed=1)
        plan_b = scale.BatchPlan(plan_id="p1", manifest_path=self.manifest_path, shard_count=6, seed=2)
        shards_a = scale.Sharder().shard(plan_a)
        shards_b = scale.Sharder().shard(plan_b)
        # Both still valid partitions of the same id set, seeds are free to
        # reassign case ids to different shard indices.
        self.assertTrue(scale.verify_partition(plan_a, shards_a))
        self.assertTrue(scale.verify_partition(plan_b, shards_b))


class SharderEdgeCaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest_path = _write_manifest(CASE_IDS)

    def test_shard_count_less_than_one_raises_value_error(self) -> None:
        plan = scale.BatchPlan(plan_id="p1", manifest_path=self.manifest_path, shard_count=0)
        with self.assertRaises(ValueError):
            scale.Sharder().shard(plan)

    def test_missing_manifest_raises_file_not_found_error(self) -> None:
        plan = scale.BatchPlan(plan_id="p1", manifest_path="does/not/exist.json", shard_count=2)
        with self.assertRaises(FileNotFoundError):
            scale.Sharder().shard(plan)

    def test_shard_count_greater_than_case_count_leaves_some_empty(self) -> None:
        small_manifest = _write_manifest(["only-one"])
        plan = scale.BatchPlan(plan_id="p1", manifest_path=small_manifest, shard_count=10, seed=99)
        shards = scale.Sharder().shard(plan)
        self.assertEqual(len(shards), 10)
        non_empty = [s for s in shards if s.case_ids]
        self.assertEqual(len(non_empty), 1)
        self.assertEqual(non_empty[0].case_ids, ("only-one",))
        self.assertTrue(scale.verify_partition(plan, shards))

    def test_single_shard_contains_every_case(self) -> None:
        plan = scale.BatchPlan(plan_id="p1", manifest_path=self.manifest_path, shard_count=1, seed=1)
        shards = scale.Sharder().shard(plan)
        self.assertEqual(len(shards), 1)
        self.assertEqual(list(shards[0].case_ids), sorted(CASE_IDS))


class VerifyPartitionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest_path = _write_manifest(CASE_IDS)
        self.plan = scale.BatchPlan(plan_id="p1", manifest_path=self.manifest_path, shard_count=3, seed=5)

    def test_detects_dropped_case(self) -> None:
        shards = scale.Sharder().shard(self.plan)
        broken = list(shards)
        broken[0] = scale.Shard(
            plan_id=broken[0].plan_id,
            index=broken[0].index,
            case_ids=broken[0].case_ids[1:] if broken[0].case_ids else broken[0].case_ids,
        )
        # Only meaningful if the first shard actually had a case to drop.
        if shards[0].case_ids:
            self.assertFalse(scale.verify_partition(self.plan, broken))

    def test_detects_overlap(self) -> None:
        shards = scale.Sharder().shard(self.plan)
        non_empty = [s for s in shards if s.case_ids]
        if len(non_empty) < 1:
            self.skipTest("no non-empty shard to duplicate")
        duplicated_id = non_empty[0].case_ids[0]
        broken = list(shards)
        broken.append(scale.Shard(plan_id=self.plan.plan_id, index=len(broken), case_ids=(duplicated_id,)))
        self.assertFalse(scale.verify_partition(self.plan, broken))


class ScaleSpecTest(unittest.TestCase):
    def test_spec_is_implemented(self) -> None:
        self.assertEqual(scale.SPEC.key, "scale")
        self.assertEqual(scale.SPEC.status, CapabilityStatus.IMPLEMENTED)


if __name__ == "__main__":
    unittest.main()
