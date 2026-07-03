"""P2 capability 2: Shadow AI discovery simulation (Shadow AI 发现模拟).

Implements a deterministic diff between a declared agent/tool registry and
observed synthetic inventory rows, surfacing shadow (unregistered) usage.
See docs/reference/p2-scope.md (P2 range item 2) and
docs/reference/p2-scope.md (P2 item 2). Still not wired into the
P0/P1 runner/oracle/reports; operates purely on plain dict/list inputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .base import CapabilityStatus, CapabilitySpec

# Maps an observed row's "kind" to the ShadowFinding.kind it produces when
# the observed id is not present in the matching declared set.
_FINDING_KIND_BY_OBSERVED_KIND = {
    "agent": "unregistered_agent",
    "tool": "unapproved_plugin",
}

_SEVERITY_BY_FINDING_KIND = {
    "unregistered_agent": "high",
    "unapproved_plugin": "medium",
}


@dataclass(frozen=True)
class ShadowFinding:
    """A discovered unsanctioned ("shadow") agent, tool, or integration."""

    finding_id: str
    kind: str  # e.g. "unregistered_agent", "unapproved_plugin", "rogue_endpoint"
    evidence_ref: str  # points at a synthetic fixture/trace, never live telemetry
    severity: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)


class DiscoveryScan:
    """Diffs declared registries against observed synthetic inventory rows.

    ``inventory`` is a plain dict shaped as::

        {"declared_agents": [...ids...], "declared_tools": [...ids...],
         "observed": [{"kind": "agent"|"tool", "id": "...", "evidence": "..."?}, ...]}

    Every ``observed`` entry whose id is missing from the matching declared
    set becomes a :class:`ShadowFinding`. Entries with an unrecognized
    ``kind`` are ignored (nothing to diff them against). Maps to the planned
    oracle fields ``shadow_agent_detected`` and ``unregistered_tool_flagged``.
    """

    def scan(self, inventory: dict[str, Any]) -> list[ShadowFinding]:
        declared_by_kind = {
            "agent": set(inventory.get("declared_agents", [])),
            "tool": set(inventory.get("declared_tools", [])),
        }

        findings: list[ShadowFinding] = []
        for row in inventory.get("observed", []):
            observed_kind = row.get("kind")
            observed_id = row.get("id")
            declared = declared_by_kind.get(observed_kind)
            if declared is None or observed_id in declared:
                continue  # unrecognized kind, or already declared: not shadow

            finding_kind = _FINDING_KIND_BY_OBSERVED_KIND[observed_kind]
            evidence_ref = row.get("evidence") or f"observed:{observed_kind}:{observed_id}"
            findings.append(
                ShadowFinding(
                    finding_id=f"{observed_kind}:{observed_id}",
                    kind=finding_kind,
                    evidence_ref=evidence_ref,
                    severity=_SEVERITY_BY_FINDING_KIND[finding_kind],
                )
            )

        findings.sort(key=lambda finding: (finding.kind, finding.finding_id))
        return findings


SPEC = CapabilitySpec(
    key="discovery",
    title="Shadow AI 发现模拟 / shadow AI discovery",
    module=__name__,
    roadmap_refs=("docs/reference/p2-scope.md#P2-2", "docs/reference/p2-scope.md#P2-2"),
    summary="Diff declared registries against observed traces to surface shadow agents/tools.",
    status=CapabilityStatus.IMPLEMENTED,
    planned_expected_fields=("shadow_agent_detected", "unregistered_tool_flagged"),
    planned_metrics=("shadow_detection_rate",),
)
