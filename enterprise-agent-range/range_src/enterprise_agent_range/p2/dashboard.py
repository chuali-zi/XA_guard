"""P2 capability 10: red/blue exercise dashboard & review report (攻防演练大屏和复盘报告).

Scaffold only. See docs/02-goals-and-scope.md (P2 range item 10) and
docs/13-implementation-roadmap.md (P2 item 10). No runtime wiring yet; no files
are produced in the scaffold phase.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .base import SCAFFOLD, CapabilitySpec, P2NotImplementedError


@dataclass(frozen=True)
class ExerciseFeed:
    """A snapshot of live-exercise metrics intended for the big-screen view."""

    run_id: str
    generated_at: str = ""  # ISO-8601 in a future implementation
    headline_metrics: dict[str, Any] = field(default_factory=dict)
    timeline: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class ReviewReport:
    """A post-exercise (复盘) narrative + evidence index for a run."""

    run_id: str
    summary: str = ""
    findings: tuple[dict[str, Any], ...] = ()
    evidence_index: dict[str, str] = field(default_factory=dict)


class DashboardBuilder:
    """Interface for building the exercise feed and post-exercise review report.

    Planned outputs (future): a JSON feed for the big screen and a Markdown/HTML
    review report. It will consume the existing run outputs (metrics.json,
    case-results.jsonl, ...) rather than reaching into runtime internals.
    """

    def build_feed(self, run_dir: str) -> ExerciseFeed:
        raise P2NotImplementedError("p2.dashboard.DashboardBuilder.build_feed is a scaffold stub")

    def build_review(self, run_dir: str) -> ReviewReport:
        raise P2NotImplementedError("p2.dashboard.DashboardBuilder.build_review is a scaffold stub")


SPEC = CapabilitySpec(
    key="dashboard",
    title="攻防演练大屏和复盘报告 / exercise dashboard & review report",
    module=__name__,
    roadmap_refs=("docs/02-goals-and-scope.md#P2-10", "docs/13-implementation-roadmap.md#P2-10"),
    summary="Build a live big-screen feed and a post-exercise review report from run outputs.",
    status=SCAFFOLD,
    planned_expected_fields=(),
    planned_metrics=("exercise_feed_ready", "review_report_ready"),
)
