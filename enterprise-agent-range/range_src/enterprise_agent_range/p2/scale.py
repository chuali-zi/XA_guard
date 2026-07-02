"""P2 capability 7: large-scale automated red-team runner (大规模自动化 red-team runner).

Scaffold only. See docs/02-goals-and-scope.md (P2 range item 7). No runtime
wiring yet; the existing single-process ``runner.run_cases`` is unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .base import SCAFFOLD, CapabilitySpec, P2NotImplementedError


@dataclass(frozen=True)
class BatchPlan:
    """A sharded plan for running many cases/mutations across workers."""

    plan_id: str
    manifest_path: str
    shard_count: int = 1
    seed: int = 20260701
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Shard:
    """One deterministic slice of a batch plan."""

    plan_id: str
    index: int
    case_ids: tuple[str, ...] = ()


class Sharder:
    """Interface for deterministically splitting a manifest into shards.

    Planned metrics: ``throughput_cases_per_min``, ``shard_result_consistency``.
    Determinism (fixed seed -> fixed shard assignment) is a hard requirement so
    large runs stay reproducible.
    """

    def shard(self, plan: BatchPlan) -> list[Shard]:
        raise P2NotImplementedError("p2.scale.Sharder.shard is a scaffold stub")


SPEC = CapabilitySpec(
    key="scale",
    title="大规模自动化 red-team runner / large-scale red-team runner",
    module=__name__,
    roadmap_refs=("docs/02-goals-and-scope.md#P2-7",),
    summary="Deterministically shard large manifests/mutations for reproducible batch runs.",
    status=SCAFFOLD,
    planned_expected_fields=(),
    planned_metrics=("throughput_cases_per_min", "shard_result_consistency"),
)
