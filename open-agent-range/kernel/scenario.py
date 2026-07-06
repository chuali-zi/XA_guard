"""Scenario — 场景 schema（数据）。

契约见 ``docs/architecture/decoupling-contract.md`` §1 与 ``docs/specs/SP1-kernel-design.md``。
场景 = 数据：一个 World 实例 + 声明的事实（什么机密、谁有权）+ 敞开的注入面 + 绑定的属性。

铁律：**加场景 = 加数据，不改内核。** 场景永远只是数据；内核不为某场景加 ``if scenario == X`` 分支。

本模块把"世界种子 / 背景业务流 / 注入 / oracle 期望 / 绑定的属性 id"抽象为可加载的数据结构。
工具的**执行体（handler）是代码**（见 ToolSurface），场景只按名字选用；这与
"世界/注入/判据是数据"并不冲突（SP2 会把这些数据外置为 DCTG fixtures）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from kernel.injection import Injection
from kernel.oracle import OracleSpec
from kernel.seat import SeatContext
from kernel.world import DataAsset, Principal, Receiver, World


@dataclass
class Scenario:
    """一个场景实例（纯数据）。"""

    scenario_id: str
    principals: list[Principal] = field(default_factory=list)
    data_assets: list[DataAsset] = field(default_factory=list)
    receivers: list[Receiver] = field(default_factory=list)
    domain_state_seed: dict[str, Any] = field(default_factory=dict)
    # 背景"正常一天"业务流：直接落成账本事实（每项是 ledger.append 的 kwargs）。
    normal_events: list[dict[str, Any]] = field(default_factory=list)
    # SP2+ 活世界业务流：带业务时钟、队列/状态迁移和同 tick 并发批次的正常事件。
    # 仍是场景数据；内核只按通用调度语义执行，不认识具体场景或攻击。
    scheduled_events: list[dict[str, Any]] = field(default_factory=list)
    # 敞开的注入面上红队投毒的内容（数据，非脚本）。良性对照时为空。
    injections: list[Injection] = field(default_factory=list)
    # 绑定的判据 id（PropertyEngine 据此注册属性；具体属性实现在内核）。
    bound_properties: list[str] = field(default_factory=list)
    oracle: OracleSpec = field(default_factory=OracleSpec)
    seat_context: SeatContext | None = None
    # SP5 最小多 seat 竖切：一次 attempt 可顺序驱动多个席位上下文。
    # 向后兼容：旧 fixture 仍使用 seat_context；新 fixture 可提供 seat_contexts。
    seat_contexts: list[SeatContext] = field(default_factory=list)
    # 场景策略（sensitive_markers / deny_external_tools），供 PolicyOverlay / XaGuardSUT 生成 Gate3。
    policy: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Scenario":
        """从数据构建（供 SP2 externalize 为 fixtures 后加载）。"""
        seat_ctx = data.get("seat_context")
        seat_contexts = data.get("seat_contexts", [])
        return cls(
            scenario_id=data["scenario_id"],
            principals=[Principal(**p) for p in data.get("principals", [])],
            data_assets=[DataAsset(**a) for a in data.get("data_assets", [])],
            receivers=[Receiver(**r) for r in data.get("receivers", [])],
            domain_state_seed=dict(data.get("domain_state_seed", {})),
            normal_events=list(data.get("normal_events", [])),
            scheduled_events=list(data.get("scheduled_events", [])),
            injections=[Injection(**i) for i in data.get("injections", [])],
            bound_properties=list(data.get("bound_properties", [])),
            oracle=OracleSpec(**data.get("oracle", {})),
            seat_context=SeatContext(**seat_ctx) if isinstance(seat_ctx, dict) else None,
            seat_contexts=[SeatContext(**ctx) for ctx in seat_contexts if isinstance(ctx, dict)],
            policy=dict(data.get("policy", {})),
        )


def load_scenario(path: Path | str) -> Scenario:
    """从 JSON fixture 加载一个场景（SP2：加场景 = 加数据）。

    fixture 是纯数据文件，schema 与 ``Scenario.from_dict`` 对齐。未知顶层键（如 ``_comment``）被忽略。
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return Scenario.from_dict(data)


def load_injections(path: Path | str) -> list[Injection]:
    """从 JSON fixture 加载一组注入（SP3：注入 = 数据落位，非脚本）。

    接受两种形状：顶层是注入列表，或形如 ``{"injections": [...]}`` 的对象。
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    items = data["injections"] if isinstance(data, dict) else data
    return [Injection(**i) for i in items]


def with_injections(scenario: Scenario, injections: list[Injection]) -> Scenario:
    """派生一个只切换 ``injections`` 的场景副本（A/B：良性对照 vs 注入变体，仅此一个变量）。"""
    return replace(scenario, injections=list(injections))


def build_world(scenario: Scenario) -> World:
    """从场景数据构建初始世界（注入尚未应用；由 runner 在正常一天之上叠加）。"""
    world = World()
    for principal in scenario.principals:
        world.principals[principal.principal_id] = principal
    for asset in scenario.data_assets:
        world.data_assets[asset.asset_id] = asset
    for receiver in scenario.receivers:
        world.receivers[receiver.receiver_id] = receiver
    # 深拷贝种子，避免多次 build 共享可变结构。
    world.domain_state = _deepish_copy(scenario.domain_state_seed)
    return world


def _deepish_copy(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _deepish_copy(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_deepish_copy(v) for v in value]
    return value
