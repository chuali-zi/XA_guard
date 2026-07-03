"""P2 capability 7: large-scale automated red-team runner (大规模自动化 red-team runner).

See docs/reference/p2-scope.md (P2 range item 7). This module implements
deterministic manifest sharding only; it does not touch the existing
single-process ``runner.run_cases`` or any other core runtime module. It reads
plain manifest JSON (``{"cases": [{"case_id": ...}, ...]}``) and produces a
partition of case ids across shards.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .base import CapabilityStatus, CapabilitySpec


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


def _load_case_ids(manifest_path: str) -> list[str]:
    """Read a manifest and return its sorted, de-duplicated case ids.

    Raises ``FileNotFoundError`` if ``manifest_path`` does not exist.
    """

    path = Path(manifest_path)
    if not path.is_file():
        raise FileNotFoundError(f"manifest not found: {manifest_path}")
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    case_ids = {str(case["case_id"]) for case in data.get("cases", [])}
    return sorted(case_ids)


class Sharder:
    """Deterministically splits a manifest's case ids into shards.

    Planned metrics: ``throughput_cases_per_min``, ``shard_result_consistency``
    (both still require a real batch executor and are out of scope here).
    Sharding strategy: sort all case ids for a stable base ordering, then bucket
    each id by ``sha256(f"{seed}:{case_id}")`` modulo ``shard_count``. This is a
    pure function of ``(manifest contents, seed, shard_count)`` -- no clock, no
    unseeded randomness -- so the same plan always yields the same shards.
    """

    def shard(self, plan: BatchPlan) -> list[Shard]:
        if plan.shard_count < 1:
            raise ValueError(f"shard_count must be >= 1, got {plan.shard_count}")
        case_ids = _load_case_ids(plan.manifest_path)
        buckets: list[list[str]] = [[] for _ in range(plan.shard_count)]
        for case_id in case_ids:
            digest = hashlib.sha256(f"{plan.seed}:{case_id}".encode("utf-8")).hexdigest()
            bucket_index = int(digest, 16) % plan.shard_count
            buckets[bucket_index].append(case_id)
        return [
            Shard(plan_id=plan.plan_id, index=index, case_ids=tuple(sorted(bucket)))
            for index, bucket in enumerate(buckets)
        ]


def verify_partition(plan: BatchPlan, shards: list[Shard]) -> bool:
    """Verify ``shards`` is a true partition of ``plan``'s manifest case ids.

    True iff every case id from the manifest appears in exactly one shard (the
    union of shard case ids equals the manifest's case ids, with no overlap and
    nothing dropped).
    """

    expected = _load_case_ids(plan.manifest_path)
    seen: list[str] = []
    for sh in shards:
        seen.extend(sh.case_ids)
    if len(seen) != len(set(seen)):
        return False
    return sorted(seen) == expected


SPEC = CapabilitySpec(
    key="scale",
    title="大规模自动化 red-team runner / large-scale red-team runner",
    module=__name__,
    roadmap_refs=("docs/reference/p2-scope.md#P2-7",),
    summary="Deterministically shard large manifests/mutations for reproducible batch runs.",
    status=CapabilityStatus.IMPLEMENTED,
    planned_expected_fields=(),
    planned_metrics=("throughput_cases_per_min", "shard_result_consistency"),
)
