"""P2 capability 8: external benchmark fusion (外部 benchmark 与内部靶场融合).

See docs/02-goals-and-scope.md (P2 range item 8) and
docs/13-implementation-roadmap.md (P2 item 8). This module only ingests local,
offline JSON exports (a list of ``{"external_case_id","outcome",...}`` records)
-- it never performs network I/O or calls a live third-party benchmark service.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .base import CapabilityStatus, CapabilitySpec

# Per-source outcome -> range taxonomy mapping. Unknown (source, outcome) pairs
# fall back to ("UNKNOWN",) so ingestion never silently drops a record.
OUTCOME_TAXONOMY_MAP: dict[str, dict[str, tuple[str, ...]]] = {
    "agentdojo": {
        "attack_success": ("PROMPT_INJECTION",),
        "attack_failed": ("BENIGN",),
        "blocked": ("BENIGN",),
        "policy_violation": ("POLICY_VIOLATION",),
    },
    "injecagent": {
        "attack_success": ("PROMPT_INJECTION", "TOOL_MISUSE"),
        "attack_failed": ("BENIGN",),
        "blocked": ("BENIGN",),
    },
}


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
    """Imports offline external benchmark exports and maps them onto the range taxonomy.

    Planned metrics: ``benchmark_coverage``, ``fused_case_count``. Records and
    internal case results are combined into one report without importing any
    external benchmark code -- ``load`` only ever reads a local file.
    """

    def load(self, source: str, path: str) -> list[BenchmarkRecord]:
        file_path = Path(path)
        if not file_path.is_file():
            raise FileNotFoundError(f"benchmark export not found: {path}")
        with file_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, list):
            raise ValueError(f"benchmark export must be a JSON list of records: {path}")

        mapping = OUTCOME_TAXONOMY_MAP.get(source, {})
        records: list[BenchmarkRecord] = []
        for raw in data:
            external_case_id = str(raw["external_case_id"])
            outcome = str(raw["outcome"])
            mapped_taxonomy = mapping.get(outcome, ("UNKNOWN",))
            metadata = {k: v for k, v in raw.items() if k not in ("external_case_id", "outcome")}
            records.append(
                BenchmarkRecord(
                    source=source,
                    external_case_id=external_case_id,
                    outcome=outcome,
                    mapped_taxonomy=mapped_taxonomy,
                    metadata=metadata,
                )
            )
        records.sort(key=lambda record: (record.source, record.external_case_id))
        return records

    def fuse(self, records: list[BenchmarkRecord], case_results: list[dict[str, Any]]) -> dict[str, Any]:
        internal_count = len(case_results)
        external_count = len(records)

        by_source: dict[str, int] = {}
        for record in records:
            by_source[record.source] = by_source.get(record.source, 0) + 1

        taxonomy_coverage: dict[str, int] = {}
        for case_result in case_results:
            for taxonomy in case_result.get("taxonomy") or ():
                taxonomy_coverage[taxonomy] = taxonomy_coverage.get(taxonomy, 0) + 1
        for record in records:
            for taxonomy in record.mapped_taxonomy:
                taxonomy_coverage[taxonomy] = taxonomy_coverage.get(taxonomy, 0) + 1

        return {
            "internal_count": internal_count,
            "external_count": external_count,
            "fused_case_count": internal_count + external_count,
            "by_source": dict(sorted(by_source.items())),
            "taxonomy_coverage": dict(sorted(taxonomy_coverage.items())),
        }


SPEC = CapabilitySpec(
    key="benchmark",
    title="外部 benchmark 融合 / external benchmark fusion",
    module=__name__,
    roadmap_refs=("docs/02-goals-and-scope.md#P2-8", "docs/13-implementation-roadmap.md#P2-8"),
    summary="Ingest offline external benchmark exports and map them onto the range taxonomy.",
    status=CapabilityStatus.IMPLEMENTED,
    planned_expected_fields=(),
    planned_metrics=("benchmark_coverage", "fused_case_count"),
)
