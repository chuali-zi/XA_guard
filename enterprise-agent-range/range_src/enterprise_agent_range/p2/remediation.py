"""P2 capability 6: undo / compensating-action suggestions (Undo/补偿动作建议).

Scaffold only. See docs/02-goals-and-scope.md (P2 range item 6) and
docs/13-implementation-roadmap.md (P2 item 6). No runtime wiring yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .base import SCAFFOLD, CapabilitySpec, P2NotImplementedError


@dataclass(frozen=True)
class CompensatingAction:
    """A suggested action that reverses or offsets a committed side effect."""

    action_id: str
    target_side_effect_hash: str  # references a row in side-effects.jsonl
    description: str
    reversible: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class UndoLog:
    """An ordered log of compensating actions proposed for a trace."""

    trace_id: str
    actions: tuple[CompensatingAction, ...] = ()


class RemediationPlanner:
    """Interface for proposing compensating/undo actions for committed effects.

    Planned oracle fields: ``compensation_available``,
    ``irreversible_effect_flagged``. Suggestions only; the range never executes
    real destructive or reversal operations.
    """

    def plan(self, side_effects: list[dict[str, Any]]) -> UndoLog:
        raise P2NotImplementedError("p2.remediation.RemediationPlanner.plan is a scaffold stub")


SPEC = CapabilitySpec(
    key="remediation",
    title="Undo/补偿动作建议 / undo & compensating actions",
    module=__name__,
    roadmap_refs=("docs/02-goals-and-scope.md#P2-6", "docs/13-implementation-roadmap.md#P2-6"),
    summary="Propose compensating/undo actions for committed synthetic side effects (suggest-only).",
    status=SCAFFOLD,
    planned_expected_fields=("compensation_available", "irreversible_effect_flagged"),
    planned_metrics=("reversible_effect_rate",),
)
