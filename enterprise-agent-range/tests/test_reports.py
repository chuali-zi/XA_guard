from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "range_src"))

from enterprise_agent_range.io_utils import write_json, write_jsonl
from enterprise_agent_range.reports import compare_run_outputs, render_compare_html, render_html_report


class ReportOutputTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="ear-report-test-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_run_html_report_escapes_dynamic_values(self) -> None:
        html = render_html_report(
            {
                "run_id": 'run-<script>alert("x")</script>',
                "sut_adapter": "adapter<&>",
                "sut_id": "sut<&>",
                "mode": "local",
                "started_at": "2026-07-01T00:00:00+00:00",
            },
            {
                "counts": {"total_cases": 1, "valid_cases": 1, "pass": 0, "fail": 1},
                "attack_success_rate": 1.0,
            },
            [
                {
                    "case_id": "CASE-<1>",
                    "title": "title with <b>html</b>",
                    "status": "FAIL",
                    "oracle_results": [{"name": "oracle<&>", "passed": False}],
                }
            ],
        )

        self.assertIn("&lt;script&gt;", html)
        self.assertIn("title with &lt;b&gt;html&lt;/b&gt;", html)
        self.assertIn("oracle&lt;&amp;&gt;", html)
        self.assertNotIn("<script>alert", html)
        self.assertNotIn("<b>html</b>", html)

    def test_compare_outputs_shape_and_html_escaping(self) -> None:
        baseline = self.tmp / "baseline"
        candidate = self.tmp / "candidate"
        out = self.tmp / "compare"
        self._write_run(
            baseline,
            run_id="run-baseline",
            counts={"total_cases": 2, "valid_cases": 2, "pass": 1, "fail": 1},
            metrics={"attack_success_rate": 1.0},
            cases=[
                {"case_id": "EAR-001", "title": "same", "status": "PASS"},
                {"case_id": "EAR-002", "title": "baseline title", "status": "FAIL"},
            ],
        )
        self._write_run(
            candidate,
            run_id="run-candidate<script>",
            counts={"total_cases": 3, "valid_cases": 3, "pass": 2, "fail": 1},
            metrics={"attack_success_rate": 0.5},
            cases=[
                {"case_id": "EAR-001", "title": "same", "status": "PASS"},
                {"case_id": "EAR-002", "title": "candidate <b>title</b>", "status": "PASS"},
                {"case_id": "EAR-003", "title": "new", "status": "FAIL"},
            ],
        )

        paths = compare_run_outputs(baseline_dir=baseline, candidate_dir=candidate, output_dir=out)
        comparison = json.loads((out / "compare.json").read_text(encoding="utf-8"))
        html = (out / "compare.html").read_text(encoding="utf-8")

        self.assertEqual(set(paths), {"compare_json", "compare_markdown", "compare_html"})
        self.assertTrue((out / "compare.md").exists())
        self.assertEqual(comparison["counts"]["total_cases"]["delta"], 1)
        self.assertEqual(comparison["metrics"]["attack_success_rate"]["delta"], -0.5)
        self.assertEqual(comparison["cases"]["total_compared"], 3)
        self.assertEqual(comparison["cases"]["status_changed"], 2)
        self.assertEqual(comparison["cases"]["added"], 1)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("candidate &lt;b&gt;title&lt;/b&gt;", html)
        self.assertNotIn("<script>", html)
        self.assertNotIn("<b>title</b>", html)

    def test_compare_html_renderer_escapes_dynamic_values(self) -> None:
        html = render_compare_html(
            {
                "baseline": {"run_id": "base<&>", "path": "base/path"},
                "candidate": {"run_id": "cand<script>", "path": "cand/path"},
                "counts": {"fail": {"baseline": 1, "candidate": 0, "delta": -1}},
                "metrics": {},
                "cases": {"total_compared": 1, "status_changed": 1, "added": 0, "removed": 0},
                "case_statuses": [
                    {
                        "case_id": "CASE-1",
                        "title": "<img src=x>",
                        "baseline_status": "FAIL",
                        "candidate_status": "PASS",
                        "status_changed": True,
                    }
                ],
            }
        )

        self.assertIn("base&lt;&amp;&gt;", html)
        self.assertIn("cand&lt;script&gt;", html)
        self.assertIn("&lt;img src=x&gt;", html)
        self.assertNotIn("<img src=x>", html)

    def _write_run(
        self,
        path: Path,
        *,
        run_id: str,
        counts: dict[str, int],
        metrics: dict[str, float],
        cases: list[dict[str, str]],
    ) -> None:
        write_json(
            path / "run-manifest.json",
            {
                "run_id": run_id,
                "sut_id": run_id + "-sut",
                "sut_adapter": "null_adapter",
                "started_at": "2026-07-01T00:00:00+00:00",
            },
        )
        write_json(path / "metrics.json", {"counts": counts, **metrics})
        write_jsonl(path / "case-results.jsonl", cases)


if __name__ == "__main__":
    unittest.main()
