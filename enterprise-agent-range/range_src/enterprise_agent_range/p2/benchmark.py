"""P2 capability 8: external benchmark fusion (外部 benchmark 与内部靶场融合).

Scaffold only. See docs/02-goals-and-scope.md (P2 range item 8) and
docs/13-implementation-roadmap.md (P2 item 8). No runtime wiring yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .base import SCAFFOLD, CapabilitySpec, P2NotImplementedError


@dataclass(frozen=True)
class BenchmarkRecord:
    """A normalized result imported from an external benchmark.

    The range only ingests synthetic/offline exports; it never calls a live
    third-party benchmark service.
    """

    source: str  # e.g. "agentdojo", "injecagent" (offline export only)
    external_case_id: str
    outcome: str
    mapped_taxonomy: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


class BenchmarkAdapter:
    """Interface for importing and mapping external benchmark results.

    Planned metrics: ``benchmark_coverage``, ``fused_case_count``. A future
    implementation maps external records onto the range taxonomy so internal and
    external results share one report, without importing external code.
    """

    def load(self, source: str, path: str) -> list[BenchmarkRecord]:
        raise P2NotImplementedError("p2.benchmark.BenchmarkAdapter.load is a scaffold stub")

    def fuse(self, records: list[BenchmarkRecord], case_results: list[dict[str, Any]]) -> dict[str, Any]:
        raise P2NotImplementedError("p2.benchmark.BenchmarkAdapter.fuse is a scaffold stub")


SPEC = CapabilitySpec(
    key="benchmark",
    title="外部 benchmark 融合 / external benchmark fusion",
    module=__name__,
    roadmap_refs=("docs/02-goals-and-scope.md#P2-8", "docs/13-implementation-roadmap.md#P2-8"),
    summary="Ingest offline external benchmark exports and map them onto the range taxonomy.",
    status=SCAFFOLD,
    planned_expected_fields=(),
    planned_metrics=("benchmark_coverage", "fused_case_count"),
)
