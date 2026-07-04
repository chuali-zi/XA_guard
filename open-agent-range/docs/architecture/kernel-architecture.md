# 内核架构 — 通用物理引擎详解

> 层级：架构约定（跨 SP）。本文是 SP1 内核的契约蓝本。
> 原则：内核**场景无关**，绝不预置任何具体攻击或具体机密。每个单元都回答"做什么 / 怎么用 / 依赖什么"。

## 0. 包结构（SP1 目标）

```
kernel/
├── world.py            # World：仪表化世界状态
├── ledger.py           # Ledger：不可篡改地面真值账本（脊梁）
├── surface.py          # ToolSurface + ToolDefinition：仪表化工具面
├── property_engine.py  # PropertyEngine：可插拔判据
├── seat.py             # Seat 契约：agent 席位统一边界
├── sut.py              # SUT 契约：被测防护统一边界
├── oracle.py           # Oracle：从副作用+账本+审计出 verdict
└── evidence.py         # EvidenceStore：证据包与 hash 清单
```

内核只依赖标准库，可单测；不引服务框架/数据库/第三方依赖（与 SP0 边界一致）。

---

## 1. World — 仪表化世界状态

**做什么**：持有一个企业世界的当前状态，域无关。把 arena 里写死 office 的
`World(mailboxes/projects/egress)` 泛化为通用状态库：

- `principals`：人/角色/系统身份（每个可绑定 Seat）。
- `data_assets`：数据资产，每条带分级（PUBLIC/INTERNAL/CONFIDENTIAL/SECRET）与归属域。
- `sinks` / `receivers`：外发目的地及其信任边界（内部 / 外部：甲方政府客户、承包商、供应商、公网）。
- `domain_state`：各域（Office/Ops/Business Data/Dev Supply/Governance/Audit）的子状态（邮箱、工单、日志、仓库/AIBOM、注册表、审计）。
- `side_effects`：世界副作用（外发、状态变更）记录，供 Oracle/Property 读。

**怎么用**：`world = build_world(scenario)` 由场景数据构建；工具经 ToolSurface 修改它；
`world.record_side_effect(...)` 记录副作用；查询用 `world.external_sensitive_egress()` 一类的**通用**投影
（判据语义由 PropertyEngine 声明，World 只提供事实）。

**依赖**：场景数据；分级/信任边界的判定规则（`is_external`、`classification_of`）作为内核工具函数（泛化自 arena `sensitive.py`）。

> 与 arena 差异：arena 的 World 只有 mailbox/project/egress 且分级写死 office；内核 World 把"实体+分级+信任边界+多域子状态"抽象出来，新增域=加数据。

## 2. Ledger — 不可篡改地面真值账本（脊梁）

**做什么**：把每一次世界副作用与关键决策 append 成不可篡改的一条事实，构成追责与判据的唯一真相源。
详细 schema 见 [ledger-schema.md](ledger-schema.md)。

**怎么用**：`ledger.append(actor, principal, seat, role, action, tool, data_ref, classification, to, decision)`
返回带 `seq/prev_hash/hash` 的 entry；`ledger.verify_hash_chain()` 校验完整性；持久化为 append-only JSONL。

**依赖**：仅标准库（`hashlib`/`json`）。不依赖任何场景或 SUT。

> 复用 spike `Ledger` 的 hash chain，扩展身份/授权/委托链字段与持久化。

## 3. ToolSurface — 仪表化工具面

**做什么**：声明一个世界暴露哪些工具，以及每个工具的 schema、能力、风险、taint。工具只做两件事：
(1) 改变或观察世界；(2) 把事实写入账本。**工具从不判断"这是不是攻击"，也不按攻击路径分支。**

**怎么用**：复用 arena `ToolDefinition` 的结构——
`name / description / input_schema / capabilities / input_max_taint / output_taint / risk_level / metadata`，
并导出两种视图：

- `mcp_schema()`：给 agent/SUT 的 MCP 工具 schema（`{name, description, inputSchema}`）。
- `gate4_yaml()`：给 SUT（XA-Guard Gate4）的能力声明（capability/taint/risk）。

一个工具是否 `side_effect`/`egress` 写在 `metadata` 里，供 World/Oracle 识别 sink。

**依赖**：World（执行时改它）、Ledger（落账）。

> 复用 arena `surface.py`（`ToolDefinition`/`ToolSurface`/`gate4_capability_yaml`）与 `office_tools.py`/`mcp_office_server.py`。

## 4. PropertyEngine — 可插拔判据

**做什么**：把"赢"的哲学（PRD §5）落成一组**可插拔的属性**，每个属性只读账本/世界事实，回答"世界是否进入了本不该出现的地面真值状态"。把 spike 里写死的"敏感数据外发"泛化为属性插件。

**怎么用**：每个属性是 `Property(id, description, evaluate(ledger, world) -> list[Violation])`；
场景**绑定**它要用的属性集（数据声明，不改内核）。典型属性族（由场景声明具体参数）：

- 机密数据到达无权接收方（sensitive-egress）。
- 无权主体借 agent 越权完成特权动作（privilege-escalation）。
- 有害后果无法被追责（unattributable-harm，读账本链是否断裂）。
- ……可扩展、不封闭。

**依赖**：Ledger、World（只读）。不依赖 SUT、不依赖攻击如何发生。

## 5. Seat — agent 席位契约

**做什么**：统一 agent 的接入边界，让"真实 agent / 脚本替身 / 红队手动"都以同一形状影响世界，而不污染内核判据。

**怎么用**：`Seat.act(context) -> ToolAttempts`。内核提供三类实现：

- `ScriptedSeat`：离线确定性，保证无凭据可跑（回归/CI）。
- `OpenCodeSeat`：`opencode run` 驱动真实 agent（复用 arena `opencode_seat.py`），未来从一轮 action plan 扩为多轮 tool loop。
- `ManualSeat`：红队手动构造尝试（SP4 工作台用）。

`context` 携带身份/任务/可见工具面/信任边界，但**不含机密答案**。

**依赖**：ToolSurface（可调工具）、身份（来自 World principal）。

> 复用 arena `agent_seat.py`/`opencode_seat.py` 与 spike 的 `ScriptedSeatAgent`/`OpenCodeSeatAgent`。

## 6. SUT — 被测防护契约

**做什么**：统一被测防护的接入边界。SUT 拿到工具调用尝试，返回 `allow / deny / proxy` 决策，并可产出自己的审计。

**怎么用**：内核提供 `NullSUT`（直通，基线）、`GuardStubSUT`（确定性替身，测判据不虚假加固）、
`XaGuardSUT`（外部 XA-Guard，guard 模式）。XA-Guard 经 **MCP stdio** 串在 Seat 与 office server 之间，
靶场用 `PolicyOverlay` 按场景/席位生成临时 Gate3（敏感 markers→deny 外发）/Gate4（能力）配置，
经 `python -m xa_guard.server --config <生成的 yaml>` 启动。**内核不 `import xa_guard`、不改其策略**（见 [decoupling-contract.md](decoupling-contract.md)）。

XA-Guard 六关卡在配置里的形态（复用 arena `sut_xaguard.py` 的 YAML）：Gate1 输入模式、Gate2 工具风险/HITL、
Gate3 python 策略、Gate4 能力、Gate5（可关）、Gate6 审计 hash。

**依赖**：ToolSurface（能力声明）、PolicyOverlay（场景→策略）、Evidence（读其落盘审计当证据）。

> 复用 arena `sut.py`/`sut_xaguard.py`/`policy_overlay.py`。

## 7. Oracle — verdict 产出

**做什么**：综合"世界副作用 + 账本事实 + SUT 审计"产出一次 attempt 的 `Verdict`；
**只读事实、不反推 SUT 内部策略**（否则 Null 基线会被虚假加固）。

**怎么用**：`evaluate(scenario_oracle_spec, world, ledger, sut_audit) -> Verdict`，字段含
`passed / expected_decision / observed_decision / external_send_count / data_exposure / reasons`。
期望值来自场景声明的 oracle spec（数据），不写死。

**依赖**：World、Ledger、SUT 审计（只读）。

> 复用 arena `oracle.py`（`Verdict`/`evaluate`）。

## 8. Evidence — 证据包

**做什么**：固定每次 attempt 的证据文件布局与 hash 清单，保证可复算、可追责、可对照。详见 [evidence-and-accountability.md](evidence-and-accountability.md)。

**怎么用**：复用 arena `EvidenceStore`/`AttemptPaths` 的稳定路径（world-in / prompt / transcript /
tool-events / audit / world-effects / verdict / artifact-hashes / 生成的 gate3·gate4·xa-guard 配置）。

**依赖**：仅标准库 + io 工具。

---

## 9. 内核不做什么（边界）

- 不预置任何具体攻击、任何具体机密。
- 工具不预置安全拦截（allow/deny 由 SUT + Oracle 判）。
- 不反推 SUT 策略、不为通过靶场改 SUT。
- 不把攻击写成固定 JSON 步骤塞进固定位置。
