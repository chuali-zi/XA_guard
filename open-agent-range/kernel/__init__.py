"""Open Agent Range — 通用内核（物理引擎）。

本包是 SP1 内核的落地脚手架，契约蓝本见
``docs/architecture/kernel-architecture.md`` 与 ``docs/specs/SP1-kernel-design.md``。

铁律（PRD §4/§6）：内核**场景无关**，绝不预置任何具体攻击或具体机密；
加场景 = 加数据，不改内核。

模块地图：
    world.py            World：仪表化世界状态（principals/data_assets/sinks/domain_state/side_effects）
    ledger.py           Ledger：不可篡改地面真值账本（hash chain + 追责三链 + JSONL 持久化）
    surface.py          ToolDefinition + ToolSurface：仪表化工具面
    injection.py        注入面：通用 place 原语 + scheme handler（开放不封闭）
    property_engine.py  PropertyEngine：可插拔判据（从账本/世界读"赢"的属性）
    seat.py             Seat 契约：ScriptedSeat / OpenCodeSeat / ManualSeat
    sut.py              SUT 契约：NullSUT / GuardStubSUT / XaGuardSUT
    oracle.py           Oracle：从副作用 + 账本 + SUT 审计产出 Verdict
    evidence.py         EvidenceStore：证据包与 hash 清单
    scenario.py         Scenario schema：world 实例 + 声明事实 + 注入面 + 绑定属性
    demo.py             最小竖切闭环，供 `python -m kernel.demo` 跑一遍

脚手架状态：本次只搭骨架 + 跑通最小竖切；标注 ``TODO(SPx)`` 的部分由后续 agent 补齐。
"""

from __future__ import annotations

__all__ = [
    "world",
    "ledger",
    "surface",
    "injection",
    "property_engine",
    "seat",
    "sut",
    "oracle",
    "evidence",
    "scenario",
    "run",
]
