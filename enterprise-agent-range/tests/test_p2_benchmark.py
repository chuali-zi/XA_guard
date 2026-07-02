from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "range_src"))

import json
import tempfile

from enterprise_agent_range.p2 import benchmark
from enterprise_agent_range.p2.base import CapabilityStatus


def _write_export(records: list[dict]) -> str:
    fh = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    )
    json.dump(records, fh)
    fh.close()
    return fh.name


AGENTDOJO_EXPORT = [
    {"external_case_id": "ad-001", "outcome": "attack_success"},
    {"external_case_id": "ad-002", "outcome": "blocked"},
    {"external_case_id": "ad-003", "outcome": "totally_unknown_outcome"},
]

INJECAGENT_EXPORT = [
    {"external_case_id": "ia-001", "outcome": "attack_success", "note": "extra"},
    {"external_case_id": "ia-002", "outcome": "attack_failed"},
]


class BenchmarkAdapterLoadTest(unittest.TestCase):
    def test_load_maps_known_outcomes(self) -> None:
        path = _write_export(AGENTDOJO_EXPORT)
        records = benchmark.BenchmarkAdapter().load("agentdojo", path)
        by_id = {r.external_case_id: r for r in records}
        self.assertEqual(by_id["ad-001"].mapped_taxonomy, ("PROMPT_INJECTION",))
        self.assertEqual(by_id["ad-002"].mapped_taxonomy, ("BENIGN",))

    def test_load_maps_unknown_outcome_to_unknown_taxonomy(self) -> None:
        path = _write_export(AGENTDOJO_EXPORT)
        records = benchmark.BenchmarkAdapter().load("agentdojo", path)
        by_id = {r.external_case_id: r for r in records}
        self.assertEqual(by_id["ad-003"].mapped_taxonomy, ("UNKNOWN",))

    def test_load_unknown_source_maps_everything_to_unknown(self) -> None:
        path = _write_export(AGENTDOJO_EXPORT)
        records = benchmark.BenchmarkAdapter().load("some_new_benchmark", path)
        for record in records:
            self.assertEqual(record.mapped_taxonomy, ("UNKNOWN",))
            self.assertEqual(record.source, "some_new_benchmark")

    def test_load_keeps_extra_fields_as_metadata(self) -> None:
        path = _write_export(INJECAGENT_EXPORT)
        records = benchmark.BenchmarkAdapter().load("injecagent", path)
        by_id = {r.external_case_id: r for r in records}
        self.assertEqual(by_id["ia-001"].metadata, {"note": "extra"})
        self.assertEqual(by_id["ia-001"].mapped_taxonomy, ("PROMPT_INJECTION", "TOOL_MISUSE"))
        self.assertEqual(by_id["ia-002"].mapped_taxonomy, ("BENIGN",))

    def test_load_missing_file_raises_file_not_found_error(self) -> None:
        with self.assertRaises(FileNotFoundError):
            benchmark.BenchmarkAdapter().load("agentdojo", "does/not/exist.json")

    def test_load_non_list_json_raises_value_error(self) -> None:
        fh = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
        json.dump({"not": "a list"}, fh)
        fh.close()
        with self.assertRaises(ValueError):
            benchmark.BenchmarkAdapter().load("agentdojo", fh.name)

    def test_load_is_deterministic_and_sorted(self) -> None:
        path = _write_export(AGENTDOJO_EXPORT)
        records_a = benchmark.BenchmarkAdapter().load("agentdojo", path)
        records_b = benchmark.BenchmarkAdapter().load("agentdojo", path)
        self.assertEqual(records_a, records_b)
        ids = [r.external_case_id for r in records_a]
        self.assertEqual(ids, sorted(ids))


INTERNAL_CASE_RESULTS = [
    {"case_id": "P1-A-001", "case_kind": "attack_case", "status": "FAIL", "taxonomy": ["AT2.1"]},
    {"case_id": "P1-A-002", "case_kind": "attack_case", "status": "PASS", "taxonomy": ["AT3.1"]},
    {"case_id": "P1-A-003", "case_kind": "attack_case", "status": "FAIL", "taxonomy": ["AT2.1", "AT4.1"]},
]


class BenchmarkAdapterFuseTest(unittest.TestCase):
    def setUp(self) -> None:
        adapter = benchmark.BenchmarkAdapter()
        agentdojo_path = _write_export(AGENTDOJO_EXPORT)
        injecagent_path = _write_export(INJECAGENT_EXPORT)
        self.records = adapter.load("agentdojo", agentdojo_path) + adapter.load(
            "injecagent", injecagent_path
        )

    def test_fuse_counts_internal_external_and_fused(self) -> None:
        result = benchmark.BenchmarkAdapter().fuse(self.records, INTERNAL_CASE_RESULTS)
        self.assertEqual(result["internal_count"], 3)
        self.assertEqual(result["external_count"], 5)
        self.assertEqual(result["fused_case_count"], 8)

    def test_fuse_by_source_counts(self) -> None:
        result = benchmark.BenchmarkAdapter().fuse(self.records, INTERNAL_CASE_RESULTS)
        self.assertEqual(result["by_source"], {"agentdojo": 3, "injecagent": 2})

    def test_fuse_taxonomy_coverage_combines_internal_and_external(self) -> None:
        result = benchmark.BenchmarkAdapter().fuse(self.records, INTERNAL_CASE_RESULTS)
        coverage = result["taxonomy_coverage"]
        # Internal: AT2.1 x2, AT3.1 x1, AT4.1 x1
        self.assertEqual(coverage["AT2.1"], 2)
        self.assertEqual(coverage["AT3.1"], 1)
        self.assertEqual(coverage["AT4.1"], 1)
        # External (agentdojo): PROMPT_INJECTION x1, BENIGN x1, UNKNOWN x1
        # External (injecagent): PROMPT_INJECTION x1, TOOL_MISUSE x1, BENIGN x1
        self.assertEqual(coverage["PROMPT_INJECTION"], 2)
        self.assertEqual(coverage["BENIGN"], 2)
        self.assertEqual(coverage["TOOL_MISUSE"], 1)
        self.assertEqual(coverage["UNKNOWN"], 1)

    def test_fuse_is_deterministic(self) -> None:
        result_a = benchmark.BenchmarkAdapter().fuse(self.records, INTERNAL_CASE_RESULTS)
        result_b = benchmark.BenchmarkAdapter().fuse(self.records, INTERNAL_CASE_RESULTS)
        self.assertEqual(result_a, result_b)

    def test_fuse_handles_empty_inputs(self) -> None:
        result = benchmark.BenchmarkAdapter().fuse([], [])
        self.assertEqual(
            result,
            {
                "internal_count": 0,
                "external_count": 0,
                "fused_case_count": 0,
                "by_source": {},
                "taxonomy_coverage": {},
            },
        )


class BenchmarkSpecTest(unittest.TestCase):
    def test_spec_is_implemented(self) -> None:
        self.assertEqual(benchmark.SPEC.key, "benchmark")
        self.assertEqual(benchmark.SPEC.status, CapabilityStatus.IMPLEMENTED)


if __name__ == "__main__":
    unittest.main()
