"""P2 capability 10: red/blue exercise dashboard & review report (攻防演练大屏和复盘报告).

Reads existing run outputs (``metrics.json`` + ``case-results.jsonl``) from a
run directory and builds in-memory ``ExerciseFeed`` / ``ReviewReport``
objects. Writes no files — this module is a pure reader/transformer over
plain dict/list data, never the core runtime modules.

See docs/reference/p2-scope.md (P2 range item 10) and
docs/reference/p2-scope.md (P2 item 10).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from .base import CapabilityStatus, CapabilitySpec

METRICS_FILENAME = "metrics.json"
CASE_RESULTS_FILENAME = "case-results.jsonl"

_HEADLINE_METRIC_KEYS = (
    "attack_success_rate",
    "false_positive_rate",
    "utility_retention",
    "assurance_pass_rate",
    "audit_completeness",
    "audit_integrity",
    "data_exposure_rate",
    "downstream_zero_effect_rate",
    "run_audit_chain_valid",
)

EVIDENCE_INDEX_TEMPLATE = {
    "metrics": "metrics.json",
    "case_results": "case-results.jsonl",
    "audit": "audit-records.jsonl",
    "side_effects": "side-effects.jsonl",
    "report_md": "report.md",
}


@dataclass(frozen=True)
class ExerciseFeed:
    """A snapshot of live-exercise metrics intended for the big-screen view."""

    run_id: str
    generated_at: str = ""  # caller-supplied, e.g. ISO-8601
    headline_metrics: dict[str, Any] = field(default_factory=dict)
    timeline: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class ReviewReport:
    """A post-exercise (复盘) narrative + evidence index for a run."""

    run_id: str
    summary: str = ""
    findings: tuple[dict[str, Any], ...] = ()
    evidence_index: dict[str, str] = field(default_factory=dict)


def _require_run_files(run_dir: str) -> tuple[Path, Path]:
    run_path = Path(run_dir)
    metrics_path = run_path / METRICS_FILENAME
    case_results_path = run_path / CASE_RESULTS_FILENAME
    if not metrics_path.is_file():
        raise FileNotFoundError(
            f"p2.dashboard: missing {METRICS_FILENAME} in run_dir {run_dir!r}"
        )
    if not case_results_path.is_file():
        raise FileNotFoundError(
            f"p2.dashboard: missing {CASE_RESULTS_FILENAME} in run_dir {run_dir!r}"
        )
    return metrics_path, case_results_path


def _read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def _resolve_run_id(metrics: dict[str, Any], run_path: Path) -> str:
    run_id = metrics.get("run_id")
    if isinstance(run_id, str) and run_id:
        return run_id
    return run_path.name


class DashboardBuilder:
    """Builds the live exercise feed and the post-exercise review report.

    Both methods only read ``metrics.json`` / ``case-results.jsonl`` from
    ``run_dir`` via ``pathlib`` + ``json`` (stdlib only) and never write
    files or reach into runtime internals.
    """

    def build_feed(self, run_dir: str, generated_at: str = "") -> ExerciseFeed:
        metrics_path, case_results_path = _require_run_files(run_dir)
        run_path = Path(run_dir)
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        run_id = _resolve_run_id(metrics, run_path)

        headline_metrics: dict[str, Any] = {
            key: metrics[key] for key in _HEADLINE_METRIC_KEYS if key in metrics
        }
        if "counts" in metrics:
            headline_metrics["counts"] = metrics["counts"]

        tallies: dict[str, dict[str, Any]] = {}
        for row in _read_jsonl(case_results_path):
            kind = row.get("case_kind", "unknown")
            entry = tallies.setdefault(kind, {"kind": kind, "pass": 0, "fail": 0})
            status = row.get("status")
            if status == "PASS":
                entry["pass"] += 1
            elif status == "FAIL":
                entry["fail"] += 1

        timeline = tuple(tallies[kind] for kind in sorted(tallies))

        return ExerciseFeed(
            run_id=run_id,
            generated_at=generated_at,
            headline_metrics=headline_metrics,
            timeline=timeline,
        )

    def build_review(self, run_dir: str) -> ReviewReport:
        metrics_path, case_results_path = _require_run_files(run_dir)
        run_path = Path(run_dir)
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        run_id = _resolve_run_id(metrics, run_path)

        findings: list[dict[str, Any]] = []
        for row in _read_jsonl(case_results_path):
            case_kind = row.get("case_kind")
            status = row.get("status")
            is_failed_attack = case_kind == "attack_case" and status == "FAIL"
            is_benign_fp = case_kind == "benign_control" and status == "FAIL"
            if is_failed_attack or is_benign_fp:
                findings.append(
                    {
                        "case_id": row.get("case_id", ""),
                        "case_kind": case_kind,
                        "status": status,
                        "title": row.get("title", ""),
                    }
                )
        findings.sort(key=lambda item: item["case_id"])

        summary = (
            f"run {run_id}: attack_success_rate={metrics.get('attack_success_rate')}, "
            f"false_positive_rate={metrics.get('false_positive_rate')}, "
            f"utility_retention={metrics.get('utility_retention')}, "
            f"findings={len(findings)}"
        )

        return ReviewReport(
            run_id=run_id,
            summary=summary,
            findings=tuple(findings),
            evidence_index=dict(EVIDENCE_INDEX_TEMPLATE),
        )


SPEC = CapabilitySpec(
    key="dashboard",
    title="攻防演练大屏和复盘报告 / exercise dashboard & review report",
    module=__name__,
    roadmap_refs=("docs/reference/p2-scope.md#P2-10", "docs/reference/p2-scope.md#P2-10"),
    summary="Build a live big-screen feed and a post-exercise review report from run outputs.",
    status=CapabilityStatus.IMPLEMENTED,
    planned_expected_fields=(),
    planned_metrics=("exercise_feed_ready", "review_report_ready"),
)
