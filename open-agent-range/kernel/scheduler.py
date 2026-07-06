"""Business scheduler — deterministic business clock, queues, and tick batches.

This module keeps the range "alive" without turning it into a scripted attack
runner. Scenario fixtures may declare normal business events with logical ticks;
the scheduler applies generic queue/state transitions and records neutral ledger
facts. It does not inspect payloads and does not know any scenario id.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from kernel.world import SideEffect


LEDGER_KEYS = {
    "actor",
    "principal",
    "role",
    "action",
    "tool",
    "seat",
    "data_ref",
    "classification",
    "to",
    "external",
    "decision",
    "ts",
    "identity_chain",
    "authorization_chain",
    "delegation_chain",
}

PreparedEvent = tuple[int, int, int, dict[str, Any]]


@dataclass
class ScheduleRun:
    """Summary written back into ``world.domain_state['clock']`` for evidence."""

    ticks: list[dict[str, Any]] = field(default_factory=list)


def run_business_schedule(
    world: Any,
    ledger: Any,
    *,
    normal_events: list[dict[str, Any]] | None = None,
    scheduled_events: list[dict[str, Any]] | None = None,
) -> ScheduleRun:
    """Apply normal business events in deterministic logical-clock order.

    ``normal_events`` is the legacy SP2 shape: each item is directly appendable
    to the ledger. ``scheduled_events`` is the richer SP2+ shape: it can carry
    queue/state transitions in addition to ledger fields. Both are normal
    business data, never attack scripts.
    """
    prepared = prepare_business_events(normal_events or [], scheduled_events or [])
    run = ScheduleRun()
    if not prepared:
        _clock(world).setdefault("current_ts", 0)
        return run

    index = 0
    while index < len(prepared):
        ts = prepared[index][0]
        batch: list[tuple[int, int, int, dict[str, Any]]] = []
        while index < len(prepared) and prepared[index][0] == ts:
            batch.append(prepared[index])
            index += 1
        set_current_tick(world, ts)
        tick_info = {
            "ts": ts,
            "concurrent": len(batch) > 1,
            "event_ids": [str(event.get("event_id", f"event-{order + 1}")) for _, _, order, event in batch],
        }
        run.ticks.append(tick_info)
        for _, _, _, event in batch:
            _apply_event(world, ledger, event, ts)

    clock = _clock(world)
    clock["ticks"] = run.ticks
    clock["last_ts"] = run.ticks[-1]["ts"]
    return run


def set_current_tick(world: Any, ts: int) -> None:
    """Set the current business tick in world state for tool handlers."""
    _clock(world)["current_ts"] = int(ts)


def current_tick(world: Any) -> int:
    clock = world.domain_state.get("clock", {})
    if isinstance(clock, dict):
        return int(clock.get("current_ts", 0) or 0)
    return 0


def prepare_business_events(
    normal_events: list[dict[str, Any]], scheduled_events: list[dict[str, Any]]
) -> list[PreparedEvent]:
    """Return deterministic business events as ``(ts, priority, order, event)`` rows."""
    return _prepare_events(normal_events, scheduled_events)


def apply_business_event(world: Any, ledger: Any, event: dict[str, Any], ts: int) -> None:
    """Apply one prepared business event at ``ts``.

    This is used by the live day runner so scheduler events can share one clock
    with seat/SUT activity instead of being replayed as a whole tape first.
    """
    _apply_event(world, ledger, event, ts)


def _prepare_events(
    normal_events: list[dict[str, Any]], scheduled_events: list[dict[str, Any]]
) -> list[PreparedEvent]:
    prepared: list[PreparedEvent] = []
    order = 0
    for event in normal_events:
        item = dict(event)
        item.setdefault("event_id", f"normal-{order + 1}")
        prepared.append((_event_ts(item), _event_priority(item), order, item))
        order += 1
    for event in scheduled_events:
        item = dict(event)
        item.setdefault("event_id", f"scheduled-{order + 1}")
        prepared.append((_event_ts(item), _event_priority(item), order, item))
        order += 1
    prepared.sort(key=lambda row: (row[0], row[1], row[2]))
    return prepared


def _event_ts(event: dict[str, Any]) -> int:
    value = event.get("ts", 0)
    return int(value if value is not None else 0)


def _event_priority(event: dict[str, Any]) -> int:
    value = event.get("priority", 100)
    return int(value if value is not None else 100)


def _apply_event(world: Any, ledger: Any, event: dict[str, Any], ts: int) -> None:
    for op in _as_list(event.get("queue_op")) + _as_list(event.get("queue_ops")):
        if isinstance(op, dict):
            _apply_queue_op(world, op, event, ts)
    for change in _as_list(event.get("state_change")) + _as_list(event.get("state_changes")):
        if isinstance(change, dict):
            _apply_state_change(world, change, event, ts)

    if event.get("record_ledger", event.get("ledger", True)) is False:
        return
    kwargs = {key: event[key] for key in LEDGER_KEYS if key in event}
    kwargs.setdefault("actor", str(event.get("actor", event.get("principal", "system"))))
    kwargs.setdefault("principal", str(event.get("principal", kwargs["actor"])))
    kwargs.setdefault("role", str(event.get("role", "")))
    kwargs.setdefault("action", str(event.get("action", "business_event")))
    kwargs.setdefault("tool", str(event.get("tool", kwargs["action"])))
    kwargs["ts"] = ts
    ledger.append(**kwargs)


def _apply_queue_op(world: Any, op: dict[str, Any], event: dict[str, Any], ts: int) -> None:
    queue_name = str(op.get("queue", ""))
    if not queue_name:
        return
    queues = world.domain_state.setdefault("queues", {})
    if not isinstance(queues, dict):
        queues = {}
        world.domain_state["queues"] = queues
    items = queues.setdefault(queue_name, [])
    if not isinstance(items, list):
        items = []
        queues[queue_name] = items

    kind = str(op.get("op", "enqueue"))
    if kind == "enqueue":
        item = dict(op.get("item", {}))
        item_id = str(op.get("item_id", item.get("id", event.get("event_id", ""))))
        if item_id:
            item.setdefault("id", item_id)
        item.setdefault("status", str(op.get("status", "pending")))
        item.setdefault("enqueued_ts", ts)
        item["updated_ts"] = ts
        items.append(item)
        _record_state_effect(world, event, ts, "queue_enqueue", {"queue": queue_name, "item": item})
        return

    item = _find_queue_item(items, str(op.get("item_id", "")))
    if item is None:
        if not op.get("create_missing", False):
            return
        item = {"id": str(op.get("item_id", event.get("event_id", ""))), "enqueued_ts": ts}
        items.append(item)

    if kind == "retry":
        item["attempts"] = int(item.get("attempts", 0) or 0) + 1
        item["status"] = str(op.get("status", "retrying"))
    elif kind == "dead_letter":
        item["status"] = "dead_letter"
    elif kind in {"approve", "approved"}:
        item["status"] = "approved"
    elif kind in {"reject", "rejected"}:
        item["status"] = "rejected"
    elif kind == "timeout":
        item["status"] = "timeout"
    else:
        item["status"] = str(op.get("status", kind))
    for key, value in dict(op.get("updates", {})).items():
        item[key] = value
    item["updated_ts"] = ts
    _record_state_effect(
        world,
        event,
        ts,
        "queue_transition",
        {"queue": queue_name, "item_id": item.get("id"), "status": item.get("status")},
    )


def _find_queue_item(items: list[Any], item_id: str) -> dict[str, Any] | None:
    if not item_id:
        return None
    for item in items:
        if not isinstance(item, dict):
            continue
        ids = {
            str(item.get("id", "")),
            str(item.get("ticket_id", "")),
            str(item.get("approval_ticket", "")),
            str(item.get("build_id", "")),
        }
        if item_id in ids:
            return item
    return None


def _apply_state_change(world: Any, change: dict[str, Any], event: dict[str, Any], ts: int) -> None:
    path = change.get("path")
    if isinstance(path, str):
        parts = [part for part in path.split(".") if part]
    elif isinstance(path, list):
        parts = [str(part) for part in path if str(part)]
    else:
        return
    if not parts:
        return
    target = world.domain_state
    for part in parts[:-1]:
        child = target.setdefault(part, {})
        if not isinstance(child, dict):
            child = {}
            target[part] = child
        target = child
    target[parts[-1]] = change.get("value")
    _record_state_effect(
        world,
        event,
        ts,
        "state_change",
        {"path": ".".join(parts), "value": change.get("value")},
    )


def _record_state_effect(world: Any, event: dict[str, Any], ts: int, action: str, payload: dict[str, Any]) -> None:
    actor = str(event.get("actor", event.get("principal", "system")))
    world.record_side_effect(
        SideEffect(
            kind="state_change",
            actor=actor,
            tool=str(event.get("tool", event.get("action", action))),
            payload={"ts": ts, "event_id": event.get("event_id", ""), "action": action, **payload},
        )
    )


def _clock(world: Any) -> dict[str, Any]:
    clock = world.domain_state.setdefault("clock", {})
    if not isinstance(clock, dict):
        clock = {}
        world.domain_state["clock"] = clock
    return clock


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]
