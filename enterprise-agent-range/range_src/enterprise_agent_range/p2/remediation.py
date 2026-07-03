"""P2 capability 6: undo / compensating-action suggestions (Undo/补偿动作建议).

Implements deterministic, suggestion-only compensating-action planning over
plain side-effect rows (see reports/*/side-effects.jsonl: ``sink_type``,
``operation``, ``payload_hash``, ``committed``, ...). See
docs/reference/p2-scope.md (P2 range item 6) and
docs/reference/p2-scope.md (P2 item 6). This module never executes
any reversal, real or synthetic; it only proposes actions that a human or a
future runner integration could carry out.
"""

from __future__ import annotations

import hashlib
import json
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


def _stable_side_effect_identity(row: dict[str, Any], duplicate_index: int = 0) -> str:
    """Stable row identity used to derive a unique compensating action id.

    ``payload_hash`` alone is not a unique side-effect id in P1 evidence: the
    same synthetic payload can be submitted by multiple traces. Include the
    row's stable fields and a duplicate counter so full-run planning does not
    produce colliding action ids.
    """

    identity = {
        "sink_type": str(row.get("sink_type") or ""),
        "operation": str(row.get("operation") or ""),
        "payload_hash": str(row.get("payload_hash") or ""),
        "trace_id": str(row.get("trace_id") or ""),
        "metadata": row.get("metadata") or {},
        "duplicate_index": duplicate_index,
    }
    return json.dumps(identity, sort_keys=True, separators=(",", ":"), default=str)


def _action_id(row: dict[str, Any], duplicate_index: int = 0) -> str:
    """Deterministic action id derived from the side-effect row identity."""

    digest = hashlib.sha256(
        _stable_side_effect_identity(row, duplicate_index).encode("utf-8")
    ).hexdigest()
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
        identity_counts: dict[str, int] = {}
        for row in side_effects:
            if not row.get("committed"):
                continue

            sink_type = str(row.get("sink_type") or "")
            payload_hash = str(row.get("payload_hash") or "")
            operation = str(row.get("operation") or "")
            side_effect_trace_id = str(row.get("trace_id") or "")
            identity = _stable_side_effect_identity(row)
            duplicate_index = identity_counts.get(identity, 0)
            identity_counts[identity] = duplicate_index + 1
            key = sink_type.lower()
            actions.append(
                CompensatingAction(
                    action_id=_action_id(row, duplicate_index),
                    target_side_effect_hash=payload_hash,
                    description=_SINK_DESCRIPTIONS.get(key, _DEFAULT_DESCRIPTION),
                    reversible=_SINK_REVERSIBLE.get(key, _DEFAULT_REVERSIBLE),
                    metadata={
                        "sink_type": sink_type,
                        "operation": operation,
                        "trace_id": side_effect_trace_id,
                    },
                )
            )

        actions.sort(key=lambda action: action.action_id)
        return UndoLog(trace_id=trace_id, actions=tuple(actions))


SPEC = CapabilitySpec(
    key="remediation",
    title="Undo/补偿动作建议 / undo & compensating actions",
    module=__name__,
    roadmap_refs=("docs/reference/p2-scope.md#P2-6", "docs/reference/p2-scope.md#P2-6"),
    summary="Propose compensating/undo actions for committed synthetic side effects (suggest-only).",
    status=CapabilityStatus.IMPLEMENTED,
    planned_expected_fields=("compensation_available", "irreversible_effect_flagged"),
    planned_metrics=("reversible_effect_rate",),
)
