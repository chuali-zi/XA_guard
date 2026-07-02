"""P2 capability 6: undo / compensating-action suggestions (Undo/补偿动作建议).

Implements deterministic, suggestion-only compensating-action planning over
plain side-effect rows (see reports/*/side-effects.jsonl: ``sink_type``,
``operation``, ``payload_hash``, ``committed``, ...). See
docs/02-goals-and-scope.md (P2 range item 6) and
docs/13-implementation-roadmap.md (P2 item 6). This module never executes
any reversal, real or synthetic; it only proposes actions that a human or a
future runner integration could carry out.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from .base import CapabilitySpec, CapabilityStatus

# --- Documented per-sink-type remediation guidance --------------------------

_SINK_DESCRIPTIONS: dict[str, str] = {
    "payment": "submit reversal/hold request",
    "email": "send retraction notice",
    "mail": "send retraction notice",  # observed alias for "email" in P1 data
    "plugin": "quarantine and uninstall",
    "http": "revoke/rotate exposed token",
    "egress": "revoke/rotate exposed token",  # alias for network egress sinks
    "service": "restore previous service state",
    "notification": "post correction notice",
}
_DEFAULT_DESCRIPTION = "manual review"

# Whether a suggested compensating action for the sink type is plausibly
# reversible. Sinks that already pushed data/notice outside the range
# (email/http-style egress) are conservatively marked irreversible: the
# recipient already saw the payload, so "undo" can only mitigate, not erase.
_SINK_REVERSIBLE: dict[str, bool] = {
    "payment": True,
    "service": True,
    "plugin": True,
    "notification": True,
    "email": False,
    "mail": False,
    "http": False,
    "egress": False,
}
_DEFAULT_REVERSIBLE = False  # unknown sinks default to the conservative case


@dataclass(frozen=True)
class CompensatingAction:
    """A suggested action that reverses or offsets a committed side effect.

    Suggestion only: nothing in this module executes the action.
    """

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


def _action_id(sink_type: str, payload_hash: str) -> str:
    """Deterministic action id derived from sink type + payload hash.

    Same ``(sink_type, payload_hash)`` always yields the same id, so
    re-planning the same evidence never produces churn.
    """

    digest = hashlib.sha256(f"{sink_type}:{payload_hash}".encode("utf-8")).hexdigest()
    return f"undo-{digest[:16]}"


class RemediationPlanner:
    """Proposes compensating/undo actions for committed side effects.

    Planned oracle fields: ``compensation_available``,
    ``irreversible_effect_flagged``. Suggestions only; the range never
    executes real destructive or reversal operations.
    """

    def plan(self, side_effects: list[dict[str, Any]], trace_id: str = "") -> UndoLog:
        """Build an :class:`UndoLog` for ``side_effects``.

        ``side_effects`` is a list of plain dicts shaped like rows in
        ``side-effects.jsonl`` (``sink_type``, ``operation``,
        ``payload_hash``, ``committed``, ...). Rows with ``committed`` falsy
        are ignored: nothing to compensate for if it never took effect.
        Every committed row yields exactly one :class:`CompensatingAction`.
        The result is sorted deterministically by ``action_id``.
        """

        actions: list[CompensatingAction] = []
        for row in side_effects:
            if not row.get("committed"):
                continue

            sink_type = str(row.get("sink_type") or "")
            payload_hash = str(row.get("payload_hash") or "")
            key = sink_type.lower()
            actions.append(
                CompensatingAction(
                    action_id=_action_id(sink_type, payload_hash),
                    target_side_effect_hash=payload_hash,
                    description=_SINK_DESCRIPTIONS.get(key, _DEFAULT_DESCRIPTION),
                    reversible=_SINK_REVERSIBLE.get(key, _DEFAULT_REVERSIBLE),
                    metadata={
                        "sink_type": sink_type,
                        "operation": str(row.get("operation") or ""),
                    },
                )
            )

        actions.sort(key=lambda action: action.action_id)
        return UndoLog(trace_id=trace_id, actions=tuple(actions))


SPEC = CapabilitySpec(
    key="remediation",
    title="Undo/补偿动作建议 / undo & compensating actions",
    module=__name__,
    roadmap_refs=("docs/02-goals-and-scope.md#P2-6", "docs/13-implementation-roadmap.md#P2-6"),
    summary="Propose compensating/undo actions for committed synthetic side effects (suggest-only).",
    status=CapabilityStatus.IMPLEMENTED,
    planned_expected_fields=("compensation_available", "irreversible_effect_flagged"),
    planned_metrics=("reversible_effect_rate",),
)
