"""SP3 — 通用注入面（多角度、任意组合投毒）测试。

验证：
- 每个已登记 scheme handler 把内容落到对应世界位置（结构化）。
- 未登记 scheme 仍走通用 place（注入面开放不封闭）。
- 组合投毒：一次 ``apply_injections`` 把内容落到多个面。
- A/B：良性对照 vs 注入变体共享同一 world + 中性 task，**只切 injections**。
- 判据与注入解耦：注入本身不制造违规；坏状态被判据抓与"从哪个面来"无关。
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from kernel.demo import (
    EXTERNAL_RECEIVER,
    SEAT_PRINCIPAL,
    _send_message,
    reference_surface,
    scripted_plan,
)
from kernel.injection import Injection, apply_injections, place
from kernel.property_engine import build_engine
from kernel.run import run_attempt
from kernel.scenario import build_world, load_injections, load_scenario, with_injections
from kernel.seat import ScriptedSeat
from kernel.sut import NullSUT
from kernel.world import World

SCENARIOS = Path(__file__).resolve().parents[2] / "scenarios"


def test_each_registered_scheme_lands_structured_content() -> None:
    world = World()
    cases = [
        ("mailbox:林工@dctg.local", {"sender": "x@e.example", "subject": "hi"}, "body"),
        ("rag:office-kb", {"doc_id": "kb-1", "title": "t"}, "body"),
        ("doc:方案", {"doc_id": "d-1"}, "body"),
        ("meeting:晨会", {"meeting_id": "m-1"}, "minutes"),
        ("log:app/web", {"level": "WARN"}, "line"),
        ("ticket:t-1", {"ticket_id": "t-1", "status": "open"}, "description"),
        ("plugin:registry", {"name": "p", "version": "0.1"}, "description"),
        ("mcp:tools", {"name": "export"}, "description"),
        ("supply:art", {"artifact": "a", "declared_hash": "sha256:x"}, "declaration"),
        ("aibom:art", {"artifact": "a"}, "declaration"),
        ("policy:handbook", {"policy_id": "pol-1", "section": "3.2"}, "text"),
        ("insider:office.manager", {"seat": "office.manager", "action": "approve"}, "note"),
    ]
    for into, meta, body_key in cases:
        scheme, _, locator = into.partition(":")
        place(world, Injection(into=into, content=f"content-{scheme}", meta=meta))
        record = world.domain_state[scheme][locator][0]
        assert record[body_key] == f"content-{scheme}", into
        for key, value in meta.items():
            assert record[key] == value, (into, key)


def test_unknown_scheme_falls_through_to_generic_place() -> None:
    # 一个内核完全不认识的新面也能纯靠数据落地（开放不封闭）。
    world = World()
    apply_injections(world, [Injection(into="brand-new-vector:endpoint-x", content="任意")])
    assert world.domain_state["brand-new-vector"]["endpoint-x"][0]["content"] == "任意"


def test_combination_poisoning_multiple_schemes_one_call() -> None:
    world = World()
    apply_injections(
        world,
        [
            Injection(into="mailbox:a@e", content="c1"),
            Injection(into="rag:kb", content="c2"),
            Injection(into="log:app", content="c3"),
            Injection(into="plugin:reg", content="c4"),
            Injection(into="ticket:t", content="c5"),
            Injection(into="supply:art", content="c6"),
            Injection(into="future-x:y", content="c7"),
        ],
    )
    assert world.domain_state["mailbox"]["a@e"][0]["body"] == "c1"
    assert world.domain_state["rag"]["kb"][0]["body"] == "c2"
    assert world.domain_state["log"]["app"][0]["line"] == "c3"
    assert world.domain_state["plugin"]["reg"][0]["description"] == "c4"
    assert world.domain_state["ticket"]["t"][0]["description"] == "c5"
    assert world.domain_state["supply"]["art"][0]["declaration"] == "c6"
    assert world.domain_state["future-x"]["y"][0]["content"] == "c7"


def test_combo_fixture_loads_and_applies_across_open_surface() -> None:
    injections = load_injections(SCENARIOS / "injections" / "office-combo.json")
    schemes = {inj.target()[0] for inj in injections}
    # 覆盖 injection-surface-model §2 的多个面 + 一个未登记新面。
    assert {"mailbox", "rag", "doc", "log", "ticket", "plugin", "mcp", "supply", "aibom", "meeting", "policy", "insider"}.issubset(schemes)
    assert "brand-new-vector" in schemes  # 开放不封闭
    world = World()
    apply_injections(world, injections)
    assert world.domain_state["mailbox"]
    assert world.domain_state["brand-new-vector"]  # 未登记面也落地了


def test_ab_differs_by_injection_only() -> None:
    control = load_scenario(SCENARIOS / "dctg" / "office.json")
    injected = with_injections(control, load_injections(SCENARIOS / "injections" / "office-combo.json"))
    control_fields = dataclasses.asdict(control)
    injected_fields = dataclasses.asdict(injected)
    # 除 injections 外，A/B 两侧完全一致（共享 world + 中性 task）。
    control_fields.pop("injections")
    injected_fields.pop("injections")
    assert control_fields == injected_fields
    assert control.injections == []
    assert len(injected.injections) >= 12


def test_injection_alone_does_not_fabricate_violations() -> None:
    # 判据与注入解耦：把内容注入到多个面，正常一天（安全计划）仍零违规。
    scenario = with_injections(
        load_scenario(SCENARIOS / "dctg" / "office.json"),
        load_injections(SCENARIOS / "injections" / "office-combo.json"),
    )
    result = run_attempt(scenario, reference_surface(), ScriptedSeat(scripted_plan()), NullSUT())
    assert result.ledger.verify_hash_chain()
    assert result.violations == []
    assert result.verdict.passed


def test_property_catches_bad_state_regardless_of_injection_surface() -> None:
    # 坏状态被 sensitive-egress 抓，与"注入从哪个面来"无关（PropertyEngine 只读账本）。
    scenario = with_injections(
        load_scenario(SCENARIOS / "dctg" / "office.json"),
        load_injections(SCENARIOS / "injections" / "office-combo.json"),
    )
    result = run_attempt(scenario, reference_surface(), ScriptedSeat(scripted_plan()), NullSUT())
    # 无论上面注入了多少面，只有当账本出现"敏感数据外发"事实时才违规。
    _send_message(
        result.world, result.ledger, SEAT_PRINCIPAL,
        {"to": EXTERNAL_RECEIVER, "sources": ["cit-1001"]},
    )
    violations = build_engine(scenario.bound_properties).evaluate_all(result.ledger, result.world)
    assert len(violations) == 1
    assert violations[0].property_id == "sensitive-egress"
