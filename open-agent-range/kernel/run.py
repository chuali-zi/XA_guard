"""Runner — 一次 attempt 的编排。

把核心闭环（``docs/architecture/system-overview.md`` §3）串起来：
    场景数据 → build world → apply inject → Seat 产出尝试 → SUT 裁决/执行
    → 世界落副作用 + 账本落账 → PropertyEngine 判坏状态 → Oracle 出 verdict。

Runner **不认识任何具体场景**，只认契约。换 Seat / 换 SUT / 换场景都不改这里。
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from kernel.accountability import trace_violation
from kernel.evidence import EvidenceStore
from kernel.injection import apply_injections
from kernel.ledger import Ledger
from kernel.oracle import Verdict, evaluate as oracle_evaluate
from kernel.property_engine import Violation, build_engine
from kernel.scheduler import apply_business_event, prepare_business_events, set_current_tick
from kernel.scenario import Scenario, build_world
from kernel.seat import Seat, SeatContext
from kernel.sut import SUT, ToolCall, XaGuardSUT
from kernel.surface import ToolDefinition, ToolSurface
from kernel.world import INTERNAL, SideEffect
from kernel.world import World


@dataclass
class AttemptResult:
    world: World
    ledger: Ledger
    verdict: Verdict
    violations: list[Violation] = field(default_factory=list)
    attempts: list[ToolCall] = field(default_factory=list)
    schedule_ticks: list[dict[str, Any]] = field(default_factory=list)


def run_attempt(
    scenario: Scenario,
    surface: ToolSurface,
    seat: Seat,
    sut: SUT,
    *,
    ledger_path: Any = None,
    evidence_store: EvidenceStore | None = None,
    evidence_meta: dict[str, Any] | None = None,
) -> AttemptResult:
    world = build_world(scenario)
    initial_world = copy.deepcopy(world.to_dict())
    ledger = Ledger(path=ledger_path)
    if isinstance(sut, XaGuardSUT) and sut.live and sut.artifacts is None:
        live_store = evidence_store or EvidenceStore(Path(".runtime") / "xa-guard-live" / scenario.scenario_id)
        sut.prepare(live_store, scenario, surface)

    # 1) 红队在敞开的注入面投毒（把 payload 当世界数据放进去，非脚本）。
    #    注入先进入世界，随后业务时钟与 seat 都在同一条 timeline 上观察它。
    apply_injections(world, scenario.injections)
    surface = _surface_with_dynamic_tools(surface, world)

    # 2) Seat 以身份领任务、产出工具调用尝试。
    #    SP5 起一个 attempt 可有多个 seat_contexts；旧场景仍走单 context。
    contexts = _seat_contexts(scenario)
    attempts: list[ToolCall] = []

    # 3) 正常业务事件与 seat/SUT activity 共用一条业务时钟。
    #    这避免"先整批放完正常日磁带，再让待测 seat 在尾巴出手"。
    schedule_ticks = _run_timeline_interleaved(
        world,
        ledger,
        scenario=scenario,
        contexts=contexts,
        seat=seat,
        sut=sut,
        surface=surface,
        attempts=attempts,
    )

    # 4) 判据从账本/世界读坏状态；Oracle 综合出 verdict。
    engine = build_engine(scenario.bound_properties)
    violations = engine.evaluate_all(ledger, world)
    verdict = oracle_evaluate(scenario.oracle, world, ledger, sut.audit, violations)

    if evidence_store is not None:
        _write_evidence(
            evidence_store,
            scenario=scenario,
            surface=surface,
            initial_world=initial_world,
            world=world,
            ledger=ledger,
            seat=seat,
            sut=sut,
            attempts=attempts,
            schedule_ticks=schedule_ticks,
            verdict=verdict,
            violations=violations,
            meta=evidence_meta or {},
        )

    return AttemptResult(
        world=world,
        ledger=ledger,
        verdict=verdict,
        violations=violations,
        attempts=attempts,
        schedule_ticks=schedule_ticks,
    )


def _run_timeline_interleaved(
    world: World,
    ledger: Ledger,
    *,
    scenario: Scenario,
    contexts: list[SeatContext],
    seat: Seat,
    sut: SUT,
    surface: ToolSurface,
    attempts: list[ToolCall],
) -> list[dict[str, Any]]:
    prepared = prepare_business_events(scenario.normal_events, scenario.scheduled_events)
    schedule_ticks: list[dict[str, Any]] = []
    states: list[dict[str, Any]] = []
    for order, context in enumerate(contexts):
        states.append(
            {
                "order": order,
                "context": context,
                "queue": [],
                "started": False,
                "steps": 0,
                "next_ts": int(getattr(context, "start_ts", 0) or 0),
                "priority": int(
                    getattr(context, "priority", 100)
                    if getattr(context, "priority", 100) is not None
                    else 100
                ),
            }
        )

    event_index = 0
    while event_index < len(prepared) or any(_state_active(state) for state in states):
        next_values: list[int] = []
        if event_index < len(prepared):
            next_values.append(prepared[event_index][0])
        next_values.extend(int(state["next_ts"]) for state in states if _state_active(state))
        if not next_values:
            break

        ts = min(next_values)
        set_current_tick(world, ts)

        if event_index < len(prepared) and prepared[event_index][0] == ts:
            batch_events: list[tuple[int, int, int, dict[str, Any]]] = []
            while event_index < len(prepared) and prepared[event_index][0] == ts:
                batch_events.append(prepared[event_index])
                event_index += 1
            tick_info = {
                "ts": ts,
                "concurrent": len(batch_events) > 1,
                "event_ids": [
                    str(event.get("event_id", f"event-{order + 1}"))
                    for _, _, order, event in batch_events
                ],
            }
            schedule_ticks.append(tick_info)
            for _, _, _, event in batch_events:
                apply_business_event(world, ledger, event, ts)

        batch = [
            state
            for state in states
            if _state_active(state) and int(state["next_ts"]) == ts
        ]
        batch.sort(key=lambda state: (state["priority"], state["order"]))
        for state in batch:
            if not state["started"]:
                surfaced = _prepare_seat_context(state["context"], world, surface)
                state["context"] = surfaced
                state["queue"] = [_as_tool_call(a) for a in seat.act(surfaced)]
                state["started"] = True
                if not state["queue"]:
                    state["next_ts"] = None
                    continue
            state["steps"] += 1
            if state["steps"] > 12:
                raise RuntimeError("seat tool loop exceeded 12 steps")
            attempt = state["queue"].pop(0)
            attempts.append(attempt)
            context = state["context"]
            output = sut.invoke(world, ledger, context.principal, attempt, surface)
            if output.get("executed") is not False:
                followups = [_as_tool_call(a) for a in seat.on_tool_result(context, attempt, output)]
                state["queue"].extend(followups)
            state["next_ts"] = ts + 1 if state["queue"] else None

    clock = world.domain_state.setdefault("clock", {})
    if isinstance(clock, dict):
        clock["ticks"] = schedule_ticks
        if schedule_ticks:
            clock["last_ts"] = max(
                [tick["ts"] for tick in schedule_ticks]
                + [entry.ts for entry in ledger.entries if entry.ts is not None]
            )
        else:
            clock.setdefault("current_ts", 0)
    return schedule_ticks


def _state_active(state: dict[str, Any]) -> bool:
    return state.get("next_ts") is not None and (not state.get("started") or bool(state.get("queue")))


def _write_evidence(
    store: EvidenceStore,
    *,
    scenario: Scenario,
    surface: ToolSurface,
    initial_world: dict[str, Any],
    world: World,
    ledger: Ledger,
    seat: Seat,
    sut: SUT,
    attempts: list[ToolCall],
    schedule_ticks: list[dict[str, Any]],
    verdict: Verdict,
    violations: list[Violation],
    meta: dict[str, Any],
) -> None:
    manifest = {
        "scenario_id": scenario.scenario_id,
        "seat_id": seat.seat_id,
        "sut_id": sut.sut_id,
        **meta,
    }
    final_world = copy.deepcopy(world.to_dict())
    store.write_json("run-manifest.json", manifest)
    store.write_json("world-in.json", initial_world)
    store.write_json("world-out.json", final_world)
    store.write_json("world-diff.json", _world_diff(initial_world, final_world))
    contexts = _seat_contexts(scenario)
    if contexts:
        prompt_lines = [
            f"principal={ctx.principal}\nrole={ctx.role}\ntask={ctx.task}\nreceiver={ctx.receiver}"
            for ctx in contexts
        ]
        store.write_text("prompt.txt", "\n\n---\n\n".join(prompt_lines) + "\n")
    store.write_jsonl(
        "tool-events.jsonl",
        [{"seq": i + 1, "tool": c.tool, "args": c.args} for i, c in enumerate(attempts)],
    )
    store.write_jsonl("timeline.jsonl", _timeline_rows(schedule_ticks, ledger, sut, attempts))
    seat_events = getattr(seat, "events", None)
    if seat_events:
        store.write_jsonl("opencode-events.jsonl", list(seat_events))
    store.write_jsonl(
        "audit.jsonl",
        [{"tool": a.tool, "decision": a.decision, "reason": a.reason} for a in sut.audit],
    )
    store.write_jsonl("world-effects.jsonl", [e.to_dict() for e in world.side_effects])
    store.write_jsonl("ledger.jsonl", [e.to_dict() for e in ledger.entries])
    store.write_json("ledger-replay.json", _ledger_replay_summary(ledger))
    store.write_json("accountability-report.json", _accountability_report(ledger, violations))
    store.write_json(
        "verdict.json",
        {
            **verdict.to_dict(),
            "violations": [v.to_dict() for v in violations],
        },
    )
    if isinstance(sut, XaGuardSUT):
        try:
            sut.write_configs(store, scenario, surface)
        except FileNotFoundError:
            pass
    store.finalize_artifact_hashes()


def _world_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    changes: list[dict[str, Any]] = []

    def walk(path: str, left: Any, right: Any) -> None:
        if isinstance(left, dict) and isinstance(right, dict):
            keys = sorted(set(left) | set(right))
            for key in keys:
                child = f"{path}.{key}" if path else str(key)
                if key not in left:
                    changes.append({"path": child, "change": "added", "current": right[key]})
                elif key not in right:
                    changes.append({"path": child, "change": "removed", "previous": left[key]})
                else:
                    walk(child, left[key], right[key])
            return
        if left != right:
            changes.append({"path": path or "$", "change": "changed", "previous": left, "current": right})

    walk("", before, after)
    return {"changed_paths": [change["path"] for change in changes], "changes": changes}


def _timeline_rows(
    schedule_ticks: list[dict[str, Any]],
    ledger: Ledger,
    sut: SUT,
    attempts: list[ToolCall],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for tick in schedule_ticks:
        rows.append({"kind": "business_tick", **tick})
    for index, call in enumerate(attempts, start=1):
        audit = sut.audit[index - 1] if index - 1 < len(sut.audit) else None
        rows.append(
            {
                "kind": "tool_attempt",
                "attempt_seq": index,
                "tool": call.tool,
                "args": call.args,
                "sut_decision": audit.decision if audit is not None else "unknown",
                "sut_reason": audit.reason if audit is not None else "",
            }
        )
    for entry in ledger.entries:
        rows.append(
            {
                "kind": "ledger_entry",
                "seq": entry.seq,
                "ts": entry.ts,
                "actor": entry.actor,
                "principal": entry.principal,
                "role": entry.role,
                "action": entry.action,
                "tool": entry.tool,
                "data_ref": entry.data_ref,
                "classification": entry.classification,
                "to": entry.to,
                "external": entry.external,
                "decision": entry.decision,
                "hash": entry.hash,
            }
        )
    return rows


def _ledger_replay_summary(ledger: Ledger) -> dict[str, Any]:
    return ledger.replay(World())


def _accountability_report(ledger: Ledger, violations: list[Violation]) -> dict[str, Any]:
    traces: list[dict[str, Any]] = []
    for violation in violations:
        trace = trace_violation(ledger, violation).to_dict()
        traces.append({"violation": violation.to_dict(), "trace": trace})
    accountable = [item["trace"].get("accountable", False) for item in traces]
    return {
        "violation_count": len(violations),
        "traces": traces,
        "all_violations_accountable": all(accountable) if accountable else True,
    }


def _prepare_seat_context(context: SeatContext, world: World, surface: ToolSurface) -> SeatContext:
    """Surface world channels and the concrete tool contract visible to this seat."""
    surfaced = _surface_visible_channels(context, world)
    return _surface_tool_contracts(surfaced, surface)


def _surface_visible_channels(context: SeatContext, world: World) -> SeatContext:
    """把注入后世界里该席位消费的**每个**通道内容投影进 ``context.visible[scheme]``。

    通用、场景无关：对席位在 ``consumed_channels()`` 里声明的每个 ``scheme:locator``，
    只读 ``world.domain_state[scheme]``（注入面默认落位处），把该 locator（或该 scheme 下全部）
    的记录列表 surface 进 ``visible[scheme]``。内核**只搬运数据、不写入任何攻击文本、不据 payload 分支**——
    内容只可能来自场景注入 / 种子数据。

    这泛化了原先仅 ``mailbox`` 一个面的读侧：任意注入面（rag/doc/log/ticket/policy/meeting…）
    只要被席位声明为消费通道，就同样端到端可被消费。``context.mailbox`` 作为向后兼容折叠进来。
    """
    channels = context.consumed_channels()
    if not channels:
        return context
    visible = dict(context.visible)
    changed = False
    for scheme, locator in channels.items():
        bucket = world.domain_state.get(scheme)
        # 只投影"locator -> 记录列表"形状的桶；跳过种子里的非结构桶（如 open_surfaces 列表）。
        if not isinstance(bucket, dict) or not bucket:
            continue
        if locator:
            records = list(bucket.get(locator, []))
        else:
            records = [r for recs in bucket.values() if isinstance(recs, list) for r in recs]
        if records:
            visible[scheme] = records
            changed = True
    if not changed:
        return context
    return replace(context, visible=visible)


def _surface_tool_contracts(context: SeatContext, surface: ToolSurface) -> SeatContext:
    """Attach ToolSurface schemas for the seat's allowed tools.

    OpenCodeSeat uses this to plan against the actual scenario tool surface instead of a
    hard-coded mail workflow. The data is a schema/description view, not world secrets.
    """
    visible = dict(context.visible)
    allowed = set(context.tool_names)
    contracts: list[dict[str, Any]] = []
    for tool in surface.tools:
        if allowed and tool.name not in allowed:
            continue
        contracts.append(
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
                "risk_level": tool.risk_level,
                "capabilities": list(tool.capabilities),
            }
        )
    if visible.get("_tool_schemas") == contracts:
        return context
    visible["_tool_schemas"] = contracts
    return replace(context, visible=visible)


def _surface_with_dynamic_tools(surface: ToolSurface, world: World) -> ToolSurface:
    """Add synthetic tools declared through plugin:/mcp: injections to this attempt surface.

    This is the first dynamic ToolSurface consequence. It does not install real plugins or
    perform network effects; it makes the declared tool visible/executable inside the range
    so SUT/seat/oracle paths can observe that the tool surface changed.
    """
    declarations = world.domain_state.get("tool_surface_declarations", [])
    if not isinstance(declarations, list):
        return surface
    existing = set(surface.tool_names())
    dynamic_tools: list[ToolDefinition] = []
    for declaration in declarations:
        if not isinstance(declaration, dict):
            continue
        tool_name = str(declaration.get("tool_name") or "").strip()
        if not tool_name or tool_name in existing:
            continue
        schema = declaration.get("input_schema", {"type": "object", "properties": {}})
        if not isinstance(schema, dict):
            schema = {"type": "object", "properties": {}}
        dynamic_tools.append(
            ToolDefinition(
                name=tool_name,
                description=str(declaration.get("description") or "Synthetic injected tool declaration."),
                input_schema=schema,
                capabilities=[str(cap) for cap in declaration.get("capabilities", [])],
                input_max_taint="CONFIDENTIAL",
                output_taint="CONFIDENTIAL",
                risk_level=str(declaration.get("risk_level") or "unknown"),
                metadata={"dynamic_tool_surface": True, **declaration},
                handler=_dynamic_tool_handler(tool_name, declaration),
            )
        )
        existing.add(tool_name)
    if not dynamic_tools:
        return surface
    return ToolSurface(name=surface.name, tools=tuple([*surface.tools, *dynamic_tools]))


def _dynamic_tool_handler(tool_name: str, declaration: dict[str, Any]) -> Any:
    def handler(world: World, ledger: Ledger, principal: str, args: dict[str, Any]) -> dict[str, Any]:
        locator = str(declaration.get("locator") or tool_name)
        ledger.append(
            actor=principal,
            principal=principal,
            role="",
            seat=principal,
            action="dynamic_tool_call",
            tool=tool_name,
            data_ref=locator,
            classification=INTERNAL,
            decision="allow",
            ts=int(world.domain_state.get("clock", {}).get("current_ts", 0) or 0)
            if isinstance(world.domain_state.get("clock", {}), dict)
            else 0,
        )
        payload = {
            "tool_name": tool_name,
            "locator": locator,
            "origin": declaration.get("origin", ""),
            "approved": bool(declaration.get("approved", False)),
            "args": dict(args),
        }
        world.record_side_effect(
            SideEffect(kind="tool_surface", actor=principal, tool=tool_name, payload=payload)
        )
        return {"dynamic_tool": tool_name, "executed": True, "approved": payload["approved"]}

    return handler


def _seat_contexts(scenario: Scenario) -> list[SeatContext]:
    if scenario.seat_contexts:
        return list(scenario.seat_contexts)
    if scenario.seat_context is not None:
        return [scenario.seat_context]
    return [SeatContext(principal="", role="", task="")]


def _as_tool_call(attempt: Any) -> ToolCall:
    if isinstance(attempt, ToolCall):
        return attempt
    if isinstance(attempt, dict):
        return ToolCall(tool=attempt["tool"], args=attempt.get("args", {}))
    raise TypeError(f"unsupported attempt type: {type(attempt)!r}")
