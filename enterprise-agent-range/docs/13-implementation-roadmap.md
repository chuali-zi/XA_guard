# 实施路线

> **2026-07-02 更新**：P0/P1/P2（下述内容）已完成并继续作为静态回放路径运行。在此之上新增了一条独立主线——**office/mail 解耦竖切（arena/）**，见文末新增章节。新的间接注入类工作应优先扩展这条主线，而不是继续在 P0/P1/P2 里加内联 `execution.steps` 的 case。

## P0：重型可演示靶场

目标：形成独立、可演示、可复现的最小重型企业靶场。

### P0.1 文档冻结

完成标准：

1. 设计说明完成。
2. 架构完成。
3. 数据模型完成。
4. 数据流完成。
5. 场景矩阵完成。
6. 指标和证据规范完成。
7. 解耦契约完成。

### P0.2 Runtime 骨架

建议新增：

```text
enterprise-agent-range/range_src/enterprise_agent_range/
```

骨架模块：

| 模块 | 职责 |
|---|---|
| `models` | 数据结构。 |
| `fixtures` | fixture 加载。 |
| `systems` | mock 业务系统。 |
| `tools` | MCP-like tools。 |
| `adapters` | SUT adapter。 |
| `runner` | case runner。 |
| `oracles` | oracle engine。 |
| `reports` | 报告生成。 |

### P0.3 Mock 系统

实现：

1. Mail sink。
2. Notification sink。
3. Ops console。
4. Business record API。
5. RAG knowledge base。
6. Plugin registry。
7. Audit store。

### P0.4 Case 与 Fixture

实现：

1. 30+ attack case。
2. 30+ benign control。
3. 10 assurance check。
4. 3+ 多步攻击链。
5. 供应链、审批、审计篡改、冒充高管付款（BEC）链路及其 fixture。

### P0.5 报告

输出：

1. `case-results.jsonl`
2. `side-effects.jsonl`
3. `audit-records.jsonl`
4. `metrics.json`
5. `report.md`
6. `artifact-hashes.json`

## P1：企业完整靶场

目标：支持长期红队和回归。

工作：

1. 扩展 100+ attack case。
2. 扩展 100+ benign control。
3. 支持多 Agent 委托链。
4. 支持 MCP stdio / HTTP。
5. 支持插件包隔离安装。
6. 支持沙箱探针。
7. 支持 mutation engine。
8. 支持 HTML 报告和对比报告。

## P2：研究级靶场

目标：做成智能体安全评测平台。

工作：

1. 多租户。
2. Shadow AI 发现模拟。
3. Agent 身份生命周期。
4. JIT 权限。
5. 风险金额量化。
6. Undo/补偿动作。
7. 攻防演练大屏。
8. 外部 benchmark 融合。
9. 第三方 TSA/HSM 证据接口。

## 优先级建议

第一轮实现顺序：

1. 数据模型和 schema。
2. fixture loader。
3. side-effect sinks。
4. null adapter。
5. oracle engine。
6. 10 个 smoke case。
7. SUT adapter。
8. 完整 P0 case。
9. 报告。

## 解耦检查点

每个阶段完成后检查：

1. 没有 `import xa_guard`。
2. 没有文件写入根 `src/`。
3. 没有新增文件写入既有 `docs/`。
4. case 期望不引用 XA-Guard 内部 rule id。
5. SUT 失败不会导致靶场自身崩溃。

## office/mail 解耦竖切（arena/，已完成）

目标：验证"环境与题库解耦、真实 agent + 真实 SUT 做决策"这套目标架构可行，见 `docs/superpowers/specs/2026-07-02-enterprise-range-decoupling-design.md`。

### 已完成（Plan 1：确定性核心）

1. `arena/world.py`：常驻有状态 World（Message/Project/EgressRecord）。
2. `arena/challenge.py`：解耦 Challenge schema（inject+task+oracle，无 steps）。
3. `arena/injection.py`：office-baseline World 构造 + 投毒注入。
4. `arena/office_tools.py`：背靠 World 的确定性工具实现。
5. `arena/sut.py`：`NullSUT`（透传）/`GuardStubSUT`（确定性规则拦截）。
6. `arena/agent_seat.py`：`GullibleAgent`（确定性最坏情形 agent 替身）。
7. `arena/oracle.py`：依据 World 副作用 + SUT 审计判分。
8. `arena/run.py`：Replay 编排器，产出攻击/对照 2×2 证据（含 A/B 防护差值）。

验证：`tests/test_arena_*.py` 全绿；仓库全量 `python -m unittest discover -s tests` 无回归。

### 已完成（Plan 2：Live 竖切）

1. Spike 确认拓扑 A 成立（`docs/superpowers/spikes/2026-07-02-xaguard-downstream-mcp.md`）：`OpenCode -> XA-Guard stdio MCP -> 任意下游 stdio MCP server`。
2. `arena/mcp_office_server.py`：真实 stdio MCP server，暴露 office 三个工具，读写同一个 World。
3. `arena/live.py` + CLI `arena-live`：生成临时 XA-Guard YAML/opencode.json/agent prompt，跑 `opencode run --format json --auto`，收 transcript+审计+副作用+verdict。
4. Live 2×2 证据（`reports/arena-live-2x2-smoke/`）：真实 OpenCode + 真实 XA-Guard 复现攻击被拦截、null 基线泄漏、良性对照两种 SUT 下均放行。
5. 旧 P1 回归无损（`reports/p1-regression-after-live/`，242 valid / 0 infra error / 0 invalid）。

### 未完成（下一步，按建议优先级）

1. **文档纠偏收尾**：本次已回填 04/05/15/16/17/13（本文件），后续每次 arena/ 架构变化应同步更新这几篇，不要再让文档漂移积累。
2. **Live 从 N=1 smoke 补成统计评测**：repeat 循环 + 置信区间 + SUT 开关 A/B 汇总报告（spec §8 已定口径，待写代码）。
3. **242 个旧 P0/P1 case 迁移**：按 spec §7.1 的分桶策略逐域迁移到 Challenge schema，`office/mail` 已迁移验证过配方，其余域待迁移；保留兼容 shim，不破坏现有回归。
4. **扩展其他域**：ops/data/dev-supply/audit 各自的间接注入场景，复用 `arena/` 架构但需要各自的 World 构造与工具面。
5. **红队台**：面向组员的注入提交/结果查看界面，spec 明确列为独立 follow-on spec，不在本阶段范围内。
