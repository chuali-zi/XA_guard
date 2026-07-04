# SP1 内核设计 — 通用物理引擎

> 状态：设计草案，待作者审后进实现。模板沿用 SP0（目标/边界/模型/判据/验收/后续）。
> 契约细节见 [../architecture/kernel-architecture.md](../architecture/kernel-architecture.md) 与 [../architecture/ledger-schema.md](../architecture/ledger-schema.md)。

## 目标

把 SP0 spike 与 `enterprise-agent-range/arena` 已验证的结构，**吸收并泛化**为一个场景无关的通用内核包，
使得"跑一个正常一天 + 判据从账本读 + Seat/SUT 可插拔"三件事都不再依赖任何具体场景代码。

三条必达：
1. 内核无任何场景专用代码即可跑完一个正常一天（场景是数据）。
2. 判据（PropertyEngine）可插拔，场景绑定其属性集。
3. 账本 hash-chain 持久化（append-only JSONL）且可校验、可重放。

## 边界

- 纯标准库，可单测；不引服务框架/数据库/第三方依赖（延续 SP0 边界）。
- 不 `import xa_guard`、不改其策略；XA-Guard 仅作 guard 模式 SUT 经 CLI/MCP 接入。
- 本 SP 不建 DCTG 全域场景（那是 SP2）；只用一个最小内联/竖切场景验证内核通用性。
- 不做通用注入面全谱（SP3）、不做工作台（SP4）、不做多 agent 追责深化（SP5）、不做看板（SP6）。

## 模型（包结构与契约）

```
kernel/
├── world.py            # World：principals/data_assets/sinks/domain_state/side_effects
├── ledger.py           # Ledger：append + hash chain + 三链 + JSONL 持久化 + verify/replay
├── surface.py          # ToolDefinition + ToolSurface（mcp_schema / gate4_yaml）
├── property_engine.py  # Property(id, evaluate(ledger, world)->[Violation]) + registry
├── seat.py             # Seat 契约：ScriptedSeat / OpenCodeSeat / ManualSeat
├── sut.py              # SUT 契约：NullSUT / GuardStubSUT / XaGuardSUT
├── oracle.py           # evaluate(oracle_spec, world, ledger, sut_audit)->Verdict
├── evidence.py         # EvidenceStore / AttemptPaths / artifact-hashes
└── scenario.py         # Scenario schema 加载（world 实例 + 声明事实 + 注入面 + 绑定属性）
```

### 移植 vs 新写清单

| 单元 | 来源 | 动作 |
|---|---|---|
| Ledger hash chain | spike `Ledger` | **移植 + 扩展**三链字段与 JSONL 持久化 |
| ToolDefinition/ToolSurface | arena `surface.py` | **移植**（含 mcp_schema/gate4_yaml/taint/capability/risk） |
| Seat（opencode） | arena `opencode_seat.py` + spike `OpenCodeSeatAgent` | **移植 + 统一**为 Seat 契约 |
| SUT（null/xaguard） | arena `sut.py`/`sut_xaguard.py` | **移植**（保留 6-gate YAML 生成与 root 定位） |
| PolicyOverlay | arena `policy_overlay.py` | **移植**（Gate3 markers→deny 外发；Gate4 能力导出） |
| Oracle/Verdict | arena `oracle.py` | **移植 + 泛化**（期望值来自 oracle_spec，不写死 send_email） |
| EvidenceStore | arena `evidence.py` | **移植** |
| World | arena `world.py` | **泛化**：从 mailbox/project/egress → 域无关 principals/data_assets/sinks/domain_state |
| PropertyEngine | spike `find_violations` | **新写**：把写死的"敏感外发"抽象为可插拔属性 registry |
| Scenario schema | spike `SCENARIO` dict | **新写**：把内联 dict 抽为数据 schema（供 SP2 外置为 fixtures） |

### 去硬编码（延续 arena refactor-plan A3）

- 判据不再写死"敏感数据外发 send_email"；改为场景声明属性集。
- Gate3 不再写死 Atlas 预算关键词；由场景 `sensitive_markers` 生成。
- Gate4 能力由 `ToolSurface` 导出，不写死 read_mail/query_project。
- 账本分级/信任边界由 `classification_of`/`is_external` 工具函数判定，参数来自场景数据。

## 判据

内核自带最小属性族（参数由场景填）：sensitive-egress、privilege-escalation、unattributable-harm（账本链断裂）。
每个属性只读 Ledger/World，产出 `Violation` 列表，不关心坏状态如何产生。

## 验收

```
# 离线确定性（无凭据可跑）
python -m kernel.demo                      # 用最小竖切场景跑一个正常一天，账本干净、hash 链 OK、零违规
python -m kernel.demo --probe-violation    # 人为追加一条坏账本事实，属性能识别
# 结构
python -m pytest kernel/tests -q           # 各单元单测通过
```

预期：
- 正常日账本干净、`verify_hash_chain()` 通过、零违规。
- 属性探针能产生并被识别（判据从账本读，与攻击路径无关）。
- 换 Seat（scripted↔opencode）、换 SUT（null↔guardstub）不改判据代码。
- 加/换场景只改数据，不改内核。

## 后续

- SP2 把最小竖切场景外置为 DCTG fixtures，并接第二个域证明"加域=加数据"。
- OpenCodeSeat 从一轮 action plan 扩为多轮 tool loop，再把 XaGuardSUT 接进真实 A/B（授权后 live）。
