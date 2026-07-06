"""SP2 — 场景数据化（fixtures）测试。

验证：
- office fixture 可经 ``load_scenario`` 从 DATA 加载并跑通竖切（等价内联参考场景）。
- 第二个域（Operations）**纯靠新增一份 fixture**接入，kernel 代码零改动即可跑通正常一天。

fixtures 在 ``open-agent-range/scenarios/``，是纯数据文件。
"""

from __future__ import annotations

from pathlib import Path

from kernel.demo import reference_surface, scripted_plan
from kernel.property_engine import build_engine
from kernel.run import run_attempt
from kernel.scenario import load_scenario
from kernel.seat import ScriptedSeat
from kernel.sut import NullSUT

SCENARIOS = Path(__file__).resolve().parents[2] / "scenarios"


def test_office_fixture_loads_from_data() -> None:
    scenario = load_scenario(SCENARIOS / "dctg" / "office.json")
    assert scenario.scenario_id == "dctg-office-baseline"
    assert scenario.bound_properties == ["sensitive-egress"]
    # 场景把"什么算机密/谁有权"都当数据声明；内核不预置。
    assert scenario.policy["sensitive_markers"] == ["居民"]
    ids = {a.asset_id for a in scenario.data_assets}
    assert {"rec-002", "cit-1001"}.issubset(ids)
    assert scenario.injections == []  # 良性对照：无注入


def test_office_fixture_runs_clean_normal_day() -> None:
    scenario = load_scenario(SCENARIOS / "dctg" / "office.json")
    result = run_attempt(scenario, reference_surface(), ScriptedSeat(scripted_plan()), NullSUT())
    assert result.ledger.verify_hash_chain()
    assert result.violations == []
    assert result.verdict.passed


def test_second_domain_is_data_only() -> None:
    # 加一个域（Operations）= 加一份 fixture；这里加载并跑通正常一天，kernel 未改。
    scenario = load_scenario(SCENARIOS / "dctg" / "ops.json")
    assert scenario.scenario_id == "dctg-ops-baseline"
    assert {p.domain for p in scenario.principals} == {"Operations"}
    # ops 竖切的正常流是背景业务事实，无外发工具调用，用空计划跑。
    result = run_attempt(scenario, reference_surface(), ScriptedSeat([]), NullSUT())
    assert result.ledger.verify_hash_chain()
    assert result.violations == []
    assert result.verdict.passed
    # 背景 F5 运维流已如实落账（read_log / restart_service）。
    actions = {e.action for e in result.ledger.entries}
    assert {"read_log", "restart_service"}.issubset(actions)


def test_both_domains_share_the_same_kernel_engine() -> None:
    # 同一套判据引擎（sensitive-egress）服务两个不同域的场景 —— 判据场景无关。
    office = load_scenario(SCENARIOS / "dctg" / "office.json")
    ops = load_scenario(SCENARIOS / "dctg" / "ops.json")
    for scenario in (office, ops):
        engine = build_engine(scenario.bound_properties)
        result = run_attempt(scenario, reference_surface(), ScriptedSeat([]), NullSUT())
        assert engine.evaluate_all(result.ledger, result.world) == []
