# Open Agent Range — 文档入口

本项目文档遵循 **"薄、分层、不写题"** 三原则（见 [PRD §4 灵魂：自由](../PRD.md)）。
文档只描述"内核和场景怎么被建模、怎么判、怎么取证"，**绝不在文档里写题目、攻击脚本或具体机密**——那些是场景数据(fixtures)，不是文档。

## 现有文档

**北极星**
- [../PRD.md](../PRD.md) — 北极星（**已冻结**）。只讲 为什么 / 是什么 / 什么感觉。

**架构约定（跨 SP 契约，`docs/architecture/`）**
- [architecture/system-overview.md](architecture/system-overview.md) — 一张图看懂内核+场景+SP+一天（入口坐标系）。
- [architecture/kernel-architecture.md](architecture/kernel-architecture.md) — 通用物理引擎逐单元详解（SP1 契约蓝本）。
- [architecture/ledger-schema.md](architecture/ledger-schema.md) — 不可篡改账本 schema、hash 链、追责三链。
- [architecture/decoupling-contract.md](architecture/decoupling-contract.md) — 内核 vs 场景、靶场 vs XA-Guard 的解耦边界。
- [architecture/injection-surface-model.md](architecture/injection-surface-model.md) — 通用注入面模型（多角度投毒）。
- [architecture/evidence-and-accountability.md](architecture/evidence-and-accountability.md) — 证据包、指标、追责与现场对照。

**参考蓝图（被建模的世界与一天，`docs/reference/`）**
- [reference/enterprise-world.md](reference/enterprise-world.md) — 数字城市科技集团（DCTG）静态世界：6 域/席位/数据/信任边界。
- [reference/a-day-in-the-life.md](reference/a-day-in-the-life.md) — DCTG 完整一天的正常业务流时间线（红队渗透的活世界）。
- [reference/attack-surface.md](reference/attack-surface.md) — AT1–AT12 × 一天触点的红队地图（不写 payload）。
- [reference/data-classification.md](reference/data-classification.md) — 合成数据资产目录与四级分级。
- [reference/expansion-roadmap.md](reference/expansion-roadmap.md) — "应该拓展什么"：世界/一天的成长路线。

**子项目设计（`docs/specs/`）**
- [specs/SP0-walking-skeleton-design.md](specs/SP0-walking-skeleton-design.md) — SP0 走通骨架（已实现于 `spike.py`）。
- [specs/SP1-kernel-design.md](specs/SP1-kernel-design.md) — 通用内核（吸收并泛化 arena + spike ledger）。
- [specs/SP2-reference-scenario-design.md](specs/SP2-reference-scenario-design.md) — DCTG 一天数据化（先竖切再拓宽）。
- [specs/SP3-injection-surface-design.md](specs/SP3-injection-surface-design.md) — 通用注入面全谱。
- [specs/SP4-redteam-workbench-design.md](specs/SP4-redteam-workbench-design.md) — 红队工作台（CLI 优先）。
- [specs/SP5-multiagent-accountability-design.md](specs/SP5-multiagent-accountability-design.md) — 多 agent 与追责。
- [specs/SP6-demo-dashboard-design.md](specs/SP6-demo-dashboard-design.md) — 现场对照 demo 与看板。
- [specs/SP7-product-completion-spec.md](specs/SP7-product-completion-spec.md) — 产品完成态总 spec：真实一天、自由注入、live SUT、判据族与验收矩阵。

## 文档分层与职责

| 层 | 位置 | 职责 | 何时写 |
|---|---|---|---|
| 北极星 | `PRD.md` | 为什么 / 是什么 / 什么感觉；冻结 | 已定稿 |
| 子项目设计 | `docs/specs/SP<N>-<topic>-design.md` | 单个 SP "怎么做"，经作者审后才进实现 | 每个 SP 开工前 |
| 产品完成态 | `docs/specs/SP7-product-completion-spec.md` | 把 SP1-SP6 串成最终验收门槛，防止把竖切误认成完成态 | 按外部 review/验收持续校准 |
| 架构约定 | `docs/architecture/*.md` | 跨 SP 的通用契约 / schema（如解耦契约、账本 schema） | 随内核成形产出，不预写 |
| 参考蓝图 | `docs/reference/*.md` | 描述被建模的企业世界与"一天"（人/角色/数据/信任边界/注入面），**非题目** | 场景蓝图定稿时产出 |
| 工作日志 | `<模块>/.log/worklog.md` | 每模块进展，每次 ≤300 字 | 持续 |

## 命名约定

- 子项目设计文档：`docs/specs/SP<N>-<topic>-design.md`，例如 `SP1-kernel-design.md`。
- **一份设计文档只对应一个 SP**，不把多个 SP 混在一起。
- 文档目录随内容产出而建，不预建空目录、不放占位符。

## 铁律（来自 PRD）

- **文档里不写"题目 / 攻击脚本 / 具体机密"。** 违反即违反自由原则。
- **PRD 已冻结。** 要改北极星必须显式走一次评审，不得顺手改。
- 每个 SP 走完整流程：设计(spec) → 计划(plan) → 实现，各自留证。
