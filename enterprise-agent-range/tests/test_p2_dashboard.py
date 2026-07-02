from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "range_src"))

from enterprise_agent_range.p2 import dashboard
from enterprise_agent_range.p2.base import CapabilityStatus

METRICS_FIXTURE = {
    "run_id": "run-test-fixture",
    "attack_success_rate": 0.5,
    "false_positive_rate": 0.25,
    "utility_retention": 0.9,
    "assurance_pass_rate": 1.0,
    "audit_completeness": 1.0,
    "audit_integrity": 1.0,
    "data_exposure_rate": 0.0,
    "downstream_zero_effect_rate": 1.0,
    "run_audit_chain_valid": True,
    "counts": {"total_cases": 4, "pass": 2, "fail": 2},
}

CASE_RESULTS_FIXTURE = [
    {
        "case_id": "P-A-001",
        "case_kind": "attack_case",
        "status": "FAIL",
        "title": "Attack one leaked data",
    },
    {
        "case_id": "P-A-002",
        "case_kind": "attack_case",
        "status": "PASS",
        "title": "Attack two blocked",
    },
    {
        "case_id": "P-B-001",
        "case_kind": "benign_control",
        "status": "FAIL",
        "title": "Benign false positive",
    },
    {
        "case_id": "P-B-002",
        "case_kind": "benign_control",
        "status": "PASS",
        "title": "Benign ok",
    },
]


def _write_run_dir(run_dir: Path, metrics: dict, case_results: list[dict]) -> None:
    (run_dir / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
    lines = "\n".join(json.dumps(row) for row in case_results)
    (run_dir / "case-results.jsonl").write_text(lines + "\n", encoding="utf-8")


class BuildFeedTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self._tmp.name)
        _write_run_dir(self.run_dir, METRICS_FIXTURE, CASE_RESULTS_FIXTURE)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_headline_metrics_reflect_metrics_json(self) -> None:
        feed = dashboard.DashboardBuilder().build_feed(str(self.run_dir), generated_at="2026-07-02T00:00:00Z")
        self.assertEqual(feed.run_id, "run-test-fixture")
        self.assertEqual(feed.generated_at, "2026-07-02T00:00:00Z")
        self.assertEqual(feed.headline_metrics["attack_success_rate"], 0.5)
        self.assertEqual(feed.headline_metrics["false_positive_rate"], 0.25)
        self.assertEqual(feed.headline_metrics["utility_retention"], 0.9)
        self.assertEqual(feed.headline_metrics["counts"], METRICS_FIXTURE["counts"])

    def test_timeline_tallies_pass_fail_per_case_kind(self) -> None:
        feed = dashboard.DashboardBuilder().build_feed(str(self.run_dir))
        by_kind = {entry["kind"]: entry for entry in feed.timeline}
        self.assertEqual(by_kind["attack_case"], {"kind": "attack_case", "pass": 1, "fail": 1})
        self.assertEqual(by_kind["benign_control"], {"kind": "benign_control", "pass": 1, "fail": 1})

    def test_timeline_is_sorted_by_kind(self) -> None:
        feed = dashboard.DashboardBuilder().build_feed(str(self.run_dir))
        kinds = [entry["kind"] for entry in feed.timeline]
        self.assertEqual(kinds, sorted(kinds))

    def test_build_feed_is_deterministic(self) -> None:
        builder = dashboard.DashboardBuilder()
        feed_a = builder.build_feed(str(self.run_dir), generated_at="t")
        feed_b = builder.build_feed(str(self.run_dir), generated_at="t")
        self.assertEqual(feed_a, feed_b)

    def test_run_id_falls_back_to_folder_name_when_absent(self) -> None:
        metrics_without_run_id = {k: v for k, v in METRICS_FIXTURE.items() if k != "run_id"}
        _write_run_dir(self.run_dir, metrics_without_run_id, CASE_RESULTS_FIXTURE)
        feed = dashboard.DashboardBuilder().build_feed(str(self.run_dir))
        self.assertEqual(feed.run_id, self.run_dir.name)


class BuildReviewTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self._tmp.name)
        _write_run_dir(self.run_dir, METRICS_FIXTURE, CASE_RESULTS_FIXTURE)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_findings_include_failed_attack_and_benign_fp(self) -> None:
        review = dashboard.DashboardBuilder().build_review(str(self.run_dir))
        case_ids = [finding["case_id"] for finding in review.findings]
        self.assertEqual(case_ids, ["P-A-001", "P-B-001"])
        by_id = {finding["case_id"]: finding for finding in review.findings}
        self.assertEqual(by_id["P-A-001"]["case_kind"], "attack_case")
        self.assertEqual(by_id["P-A-001"]["status"], "FAIL")
        self.assertEqual(by_id["P-A-001"]["title"], "Attack one leaked data")
        self.assertEqual(by_id["P-B-001"]["case_kind"], "benign_control")
        self.assertEqual(by_id["P-B-001"]["status"], "FAIL")

    def test_findings_exclude_passing_cases(self) -> None:
        review = dashboard.DashboardBuilder().build_review(str(self.run_dir))
        case_ids = {finding["case_id"] for finding in review.findings}
        self.assertNotIn("P-A-002", case_ids)
        self.assertNotIn("P-B-002", case_ids)

    def test_summary_mentions_key_numbers(self) -> None:
        review = dashboard.DashboardBuilder().build_review(str(self.run_dir))
        self.assertIn("run-test-fixture", review.summary)
        self.assertIn("0.5", review.summary)
        self.assertIn("2", review.summary)  # findings count

    def test_evidence_index_lists_expected_files(self) -> None:
        review = dashboard.DashboardBuilder().build_review(str(self.run_dir))
        self.assertEqual(
            review.evidence_index,
            {
                "metrics": "metrics.json",
                "case_results": "case-results.jsonl",
                "audit": "audit-records.jsonl",
                "side_effects": "side-effects.jsonl",
                "report_md": "report.md",
            },
        )

    def test_findings_ordering_is_deterministic(self) -> None:
        builder = dashboard.DashboardBuilder()
        review_a = builder.build_review(str(self.run_dir))
        review_b = builder.build_review(str(self.run_dir))
        self.assertEqual(review_a.findings, review_b.findings)


class MissingFileTest(unittest.TestCase):
    def test_build_feed_raises_when_metrics_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "case-results.jsonl").write_text("", encoding="utf-8")
            with self.assertRaises(FileNotFoundError):
                dashboard.DashboardBuilder().build_feed(str(run_dir))

    def test_build_feed_raises_when_case_results_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "metrics.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(FileNotFoundError):
                dashboard.DashboardBuilder().build_feed(str(run_dir))

    def test_build_review_raises_when_run_dir_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                dashboard.DashboardBuilder().build_review(tmp)


class DashboardSpecTest(unittest.TestCase):
    def test_spec_reports_implemented(self) -> None:
        self.assertEqual(dashboard.SPEC.key, "dashboard")
        self.assertEqual(dashboard.SPEC.module, dashboard.__name__)
        self.assertEqual(dashboard.SPEC.status, CapabilityStatus.IMPLEMENTED)


if __name__ == "__main__":
    unittest.main()
