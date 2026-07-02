"""P2 capability 2: Shadow AI discovery simulation (Shadow AI 发现模拟).

Scaffold only. See docs/02-goals-and-scope.md (P2 range item 2) and
docs/13-implementation-roadmap.md (P2 item 2). No runtime wiring yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .base import SCAFFOLD, CapabilitySpec, P2NotImplementedError


@dataclass(frozen=True)
class ShadowFinding:
    """A discovered unsanctioned ("shadow") agent, tool, or integration."""

    finding_id: str
    kind: str  # e.g. "unregistered_agent", "unapproved_plugin", "rogue_endpoint"
    evidence_ref: str  # points at a synthetic fixture/trace, never live telemetry
    severity: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)


class DiscoveryScan:
    """Interface for scanning synthetic inventory for shadow AI usage.

    Planned oracle fields: ``shadow_agent_detected``,
    ``unregistered_tool_flagged``. A future implementation will diff the declared
    agent/tool registry against observed traces to surface shadow usage.
    """

    def scan(self, inventory: Any) -> list[ShadowFinding]:
        raise P2NotImplementedError("p2.discovery.DiscoveryScan.scan is a scaffold stub")


SPEC = CapabilitySpec(
    key="discovery",
    title="Shadow AI 发现模拟 / shadow AI discovery",
    module=__name__,
    roadmap_refs=("docs/02-goals-and-scope.md#P2-2", "docs/13-implementation-roadmap.md#P2-2"),
    summary="Diff declared registries against observed traces to surface shadow agents/tools.",
    status=SCAFFOLD,
    planned_expected_fields=("shadow_agent_detected", "unregistered_tool_flagged"),
    planned_metrics=("shadow_detection_rate",),
)
