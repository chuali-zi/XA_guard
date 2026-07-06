# kernel — SP1 内核脚手架（补齐指南）

本目录是 SP1 内核的**脚手架**：契约、dataclass、可跑通的最小竖切都已就位；
标注 `TODO(SPx)` 的部分留给后续 agent 补齐。契约蓝本见
[`../docs/architecture/kernel-architecture.md`](../docs/architecture/kernel-architecture.md)、
[`../docs/architecture/ledger-schema.md`](../docs/architecture/ledger-schema.md)、
[`../docs/architecture/injection-surface-model.md`](../docs/architecture/injection-surface-model.md)、
[`../docs/specs/SP1-kernel-design.md`](../docs/specs/SP1-kernel-design.md)。

## 铁律（改任何模块前先读）

- 内核**场景无关**：绝不预置具体攻击、具体机密；不写 `if scenario == X` 分支。
- 加场景 = 加数据，不改内核（World/injections/properties/oracle 都是数据）。
- 注入面**开放不封闭**：`injection.place` 的通用原语必须能接住任意新 scheme，
  `SCHEME_HANDLERS` 只是便利层，**不是准入清单**。
- 账本只如实记事实，不判断/分类攻击；不落机密明文，只存 `data_ref` + 分级。
- 不 `import xa_guard`、不改其策略；XA-Guard 仅作 guard 模式 SUT 经 CLI/MCP 接入。
- 不靠改测试来"通过"；测试确实错了要先通知作者。

## 跑一遍（验证脚手架）

在 `open-agent-range/` 目录下：

```bash
python -m kernel.demo                    # 正常一天：账本干净、hash 链 OK、零违规
python -m kernel.demo --probe-violation  # 追加坏账本事实，判据识别
python -m kernel.demo --scenario scenarios/dctg/office-mailbox.json --inject scenarios/injections/office-mail-exfil.json --ab  # 现场对照：null 泄漏 vs guard 拦截
python -m kernel.demo --agent opencode --model deepseek/deepseek-v4-flash  # live，一轮 action plan，需 PATH 有 opencode
python -m kernel.demo --scenario scenarios/dctg/office-mailbox.json --agent opencode --opencode-multiround --model deepseek/deepseek-v4-flash  # live，实验性最小多轮
python -m kernel.demo --evidence-dir .runtime/demo-evidence  # 写证据包
python -m pytest kernel/tests -q         # 冒烟 + 单元测试
```

## 模块状态与补齐清单

| 模块 | 状态 | 待补（负责 SP） |
|---|---|---|
| `world.py` | 已就位（通用 World + 分级/信任边界工具函数） | 各域子状态随场景扩展（SP2） |
| `ledger.py` | hash chain / JSONL 持久化**可用**；三链字段就位，SP5 最小追责竖切已透传三链事实；`Ledger.replay()` 已有 `ledger_projection_v1`（egress、attempt/decision、关键队列/状态索引，full-day 关键终态可复原） | 更多动态工具 replay payload、Gate6/range ledger 对齐、更完整的三链语义校验（SP5/SP7） |
| `surface.py` | ToolDefinition/ToolSurface + handler 执行**可用** | 各域工具面声明（SP2） |
| `scheduler.py` | 业务时钟 / `scheduled_events` / 同 tick 并发批次 / queues 状态迁移 / retry-timeout-dead-letter **可用**（SP2+） | 持久 session、crash recover、更多跨域依赖触发 |
| `injection.py` | 通用 `place` + 多 scheme handler（mailbox/rag/doc/log/ticket/plugin/mcp/supply/aibom/meeting/policy/insider）**可用**；未登记 scheme 走通用 place；`plugin/mcp` 已记录工具面漂移 consequence，并保留声明 schema 供动态 ToolSurface 使用；`supply/aibom` 已记录供应链声明/hash/来源漂移 consequence（SP3/SP7） | insider 接 SP5 多 agent 行为；plugin/mcp 接真实 downstream/策略拦截；supply/aibom 接真实构建/包管理模拟 |
| `property_engine.py` | 契约 + `sensitive-egress`**可用**；`privilege-escalation`/`approval-bypass`/`unattributable-harm` 的 SP5 最小判据**可用**；`tool-surface-drift`/`supply-chain-drift` 语义型注入判据**可用**；`audit-integrity-break` 最小 hash-chain 判据**可用**；`policy-exception-abuse`/`sandbox-escape-attempt` 最小属性族**可用** | 属性参数化、更完整的授权/越级规则、更多真实 policy/sandbox consequence（SP5/SP7） |
| `accountability.py` | SP5 最小追责回溯**可用**：从 `Violation.ledger_seq` 沿三链点名原始主体/代劳 seat/审批票据，链断裂报不可追责 | 追责报告格式、跨 attempt 对照（SP5/SP6） |
| `seat.py` | 契约 + `ScriptedSeat`/`ScriptedMultiSeat`/`GullibleSeat`；`OpenCodeSeat` 一轮 action plan **可用**，prompt 现在读取每个 seat 的 ToolSurface contract 并支持通用 `{"tool":"...","args":{...}}` 计划格式；实验性 `multi_round=True` 支持“先读一个声明通道→基于工具输出 follow-up 决策”；`ManualSeat` 已可由 workbench 注入红队手动 ToolCall | 任意长度多轮 planner、让 full-day 更多 seat 使用 live OpenCode、交互式 ManualSeat/Web 工作台（SP4） |
| `sut.py` | 契约 + `NullSUT`/`GuardStubSUT`/`XaGuardSUT`（配置生成 + 离线 gate3 stub + 最小 live stdio MCP/Gate6 审计回读）**可用**；workbench 已能发起 Null vs XA-Guard A/B 并分离 live `INFRA_ERROR` | 长生命周期 SUT session、真实 live N>=3 证据矩阵、ledger/audit 深度对齐（SP5/SP6） |
| `policy_overlay.py` | Scenario 驱动 Gate3 规则生成**可用** | — |
| `oracle.py` | 通用 `evaluate`**可用**（期望值来自 OracleSpec，不写死工具） | 随属性族扩展（SP5） |
| `evidence.py` | EvidenceStore + hash 清单**可用**；`run_attempt` 会写真正运行前 `world-in`、`world-out`、`world-diff`、`timeline`、`ledger-replay` replay projection 和 `accountability-report` | 完整 deterministic replay、HTML/Markdown report、report/replay CLI（SP6/SP7） |
| `range_cli.py` | SP7 产品命令薄入口 **可用**：`day` 写标准 evidence + `day-summary.json`，`replay` 校验 artifact hash / ledger projection / SUT audit，`report` 输出 JSON/Markdown/HTML，`sut check` 检查 SUT overlay/live smoke，`workbench serve` 生成静态红队工作台，且顶层透出 workbench 命令别名 | 更完整交互式 HTML 看板、真实 live N>=3 矩阵、Gate6/range ledger 深度对齐 |
| `scenario.py` | Scenario schema + `from_dict` + `build_world` + `policy` 字段 + `scheduled_events` + `seat_contexts` + `load_scenario`/`load_injections`/`with_injections`**可用**（SP2+ + SP5 最小多 seat） | schema 校验、更多声明式依赖 |
| `run.py` | attempt 编排 + 可选 EvidenceStore 接线 + **通用** `_surface_visible_channels`；支持旧单 `seat_context`、SP5 多 `seat_contexts`、`Seat.on_tool_result` 工具回调循环、多 seat 按业务 tick 确定性轮转交错，把 per-seat ToolSurface schema surface 给真实 agent，以及把 approved plugin/mcp 声明加入本次 attempt 的合成动态 ToolSurface **可用** | 复杂 planner 调度、真实 MCP downstream、持久 session（SP5/SP6） |
| `ab.py` | 现场对照 A/B：同一注入变体只切 SUT（null 泄漏 vs guard 拦截），打印 ASR 对照**可用** | N≥2 统计与置信区间（SP5/SP6） |
| `demo.py` | 内联参考场景 + `--scenario` fixture 回放 + `--inject` A/B + `--ab`（现场对照）+ `--agent scripted/gullible/opencode` + 多通道读工具（`read_mail`/`read_doc`/`read_log`/`read_ticket`/`read_policy`/`read_meeting`）+ `--evidence-dir`**可用** | — |

> 注入面**可消费性**（SP3 深化）：在此之前注入只写进 `domain_state` 无人读回（惰性）。现在读侧已从
> `mailbox:` 一个面**泛化为通用机制**：`run.py._surface_visible_channels` 对席位在 `SeatContext.channels`
> （＋向后兼容的 `mailbox` 字段）声明消费的**每个** `scheme:locator`，把 `domain_state[scheme]` 的记录
> surface 进 `visible[scheme]`（纯数据搬运，内核不写攻击文本、不按 payload 分支）；`GullibleSeat` 扫描**任一**
> 可见通道里的结构化指令并照做；`sensitive-egress` 从账本抓到**涌现式**泄漏，`ab.py` 给出 null/guard 对照。
>
> **端到端可消费的 scheme**（有读工具 + 被 surface + GullibleSeat 会反应）：
> `mailbox`、`rag`/`doc`（`read_doc`）、`log`、`ticket`、`policy`、`meeting`、
> `plugin`/`mcp`（`read_tool_surface`）、`supply`/`aibom`（`read_supply_chain`）、`insider`（`read_insider`）。
> **语义后果进度**：`plugin`/`mcp` 可经 `read_tool_surface` 被读到，且未授权工具声明会进入
> `tool_surface_declarations` / `tool_surface_drift`，由 `tool-surface-drift` 属性判定；approved 声明还会进入
> 本次 attempt 的合成动态 ToolSurface，调用时只落 `dynamic_tool_call` 与 `tool_surface` side effect。
> 这仍不是完整真实插件安装或真实 MCP downstream 改写。`supply`/`aibom` 可经 `read_supply_chain` 被读到，
> 且 hash/来源/组件声明漂移会进入 `supply_chain_declarations` / `supply_chain_drift`，由
> `supply-chain-drift` 属性判定；这仍不是完整真实包管理器或构建系统模拟。`insider` 可经
> `read_insider` 被读到；它的完成态仍应建模为"多 agent 行为/权限状态变化"。
> 任何**未登记 scheme**（如 `brand-new-vector:`）仍走通用 `place` 落位（开放不封闭），只是没有读工具故不被消费——
> 这正是"可消费层是便利/消费层，不是注入准入清单"的体现。
>
> 设计取舍：这些语义型面现在已有读侧，避免红队内容完全沉默；但它们的产品完成态不是"读文本后外发"，
> 而是 `plugin/mcp` 改变工具面、`supply/aibom` 触发供应链漂移、`insider` 改变多 agent 行为/授权状态。

> SP5 最小追责竖切：`scenarios/dctg/accountability-delegation.json` 声明多 seat 委托场景；
> `ScriptedMultiSeat` 按 principal 返回各自计划；参考工具从调用参数透传
> `identity_chain` / `authorization_chain` / `delegation_chain` 到账本；
> `sensitive-egress` 命中后可用 `accountability.trace_violation()` 点名原始主体、审批票据与代劳 seat。
> 链断裂时 `unattributable-harm` 违规会出现；场景声明的 `privileged_actions` 缺审批时
> `privilege-escalation` 会命中；特权动作引用 missing/pending/timeout 审批票据时
> `approval-bypass` 会命中。`full-day.json` 的 F5 运维重启已从 scheduled tape 迁出为
> `赵工 read_log -> request_approval` 与 `钱主管 approve -> restart_service` 的真实 seat/SUT/ToolSurface 链路。
> 完整 SP5（live 多 agent、多轮工具、复杂委托拓扑、追责报告）仍待补。

## 场景 fixtures（SP2）

`open-agent-range/scenarios/` 是**纯数据**（加场景 = 加数据，不改内核）：

```
scenarios/
├── dctg/office.json           # 首个竖切：Office + Business Data 正常一天（良性对照，injections 为空）
├── dctg/ops.json              # 第二个域 Operations，纯靠这份数据接入（证明加域=加数据）
├── dctg/full-day.json         # SP2+ 六域活世界：业务时钟 + 队列 + 审批状态 + 同 tick 并发
├── dctg/office-mailbox.json   # 现场对照基底（单通道）：可反应席位（读邮件）+ 中性任务
├── dctg/office-channels.json  # 现场对照基底（多通道）：席位消费 mailbox/rag/doc/log/ticket/policy/meeting
├── dctg/accountability-delegation.json # SP5 最小追责竖切：多 seat 委托 + 三链追责
├── injections/office-combo.json       # SP3 组合投毒集：多面 + 一个未登记新面（只落位，不含结构化指令）
├── injections/office-mail-exfil.json  # 可消费注入（mailbox）：一封带结构化指令的钓鱼邮件
├── injections/office-rag-exfil.json   # 可消费注入（rag）：知识库间接注入
├── injections/office-log-exfil.json   # 可消费注入（log）：日志行间接注入
├── injections/office-ticket-exfil.json# 可消费注入（ticket）：工单描述间接注入
├── injections/office-multi-combo.json # 组合投毒（可消费）：多面同时带指令 + 一个未登记新面
└── injections/full-day-plugin-drift.json # SP7 语义型注入：plugin/mcp 未授权工具面漂移
```

```bash
python -m kernel.demo --scenario scenarios/dctg/office.json   # fixture 回放正常一天
python -m kernel.demo --scenario scenarios/dctg/office.json --inject scenarios/injections/office-combo.json  # 组合投毒落位
# 现场对照 A/B（涌现式投毒）：轻信 seat 消费注入 -> null 泄漏 / guard 拦截。换 --inject 即换注入角度：
python -m kernel.demo --scenario scenarios/dctg/office-mailbox.json --inject scenarios/injections/office-mail-exfil.json --ab
python -m kernel.demo --scenario scenarios/dctg/office-channels.json --inject scenarios/injections/office-rag-exfil.json --ab   # 知识库角度
python -m kernel.demo --scenario scenarios/dctg/office-channels.json --inject scenarios/injections/office-log-exfil.json --ab   # 日志角度
python -m kernel.demo --scenario scenarios/dctg/office-channels.json --inject scenarios/injections/office-multi-combo.json --ab # 多面组合
```

## 补齐一个 TODO 的建议流程

1. 先读对应 `docs/architecture/*` 契约段落（每个 stub 的 docstring 都指了具体文件/章节）。
2. 保持模块边界：判据只读 Ledger/World；工具不判攻击；SUT 只 allow/deny/proxy。
3. 加能力优先"加数据"（场景/属性 id/注入 content），只有确需新机制才动内核代码。
4. 补 `kernel/tests` 对应用例，`python -m pytest kernel/tests -q` 绿。
5. 更新 `../status.md`（仓库当前状态）与 `../log.md`（顶层追加工作日志）。

## 移植来源（避免重造轮子）

- Ledger hash chain：`spike.py` `Ledger`
- ToolDefinition/ToolSurface、Oracle、Evidence、SUT、PolicyOverlay、OpenCodeSeat：
  `../../enterprise-agent-range/range_src/enterprise_agent_range/arena/` 对应文件（降级为参考，**不产生 runtime 依赖**）。


