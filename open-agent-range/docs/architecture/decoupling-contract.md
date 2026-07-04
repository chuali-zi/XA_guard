# 解耦契约 — 内核 vs 场景，靶场 vs 被测防护

> 层级：架构约定（跨 SP）。本文钉死两条解耦线：**内核 vs 场景**、**靶场 vs XA-Guard**。
> 违反解耦即违反 PRD §4/§6 的自由与通用原则。

## 1. 内核 vs 场景

| | 内核 KERNEL | 场景 SCENARIO |
|---|---|---|
| 是什么 | 通用物理引擎（World/Ledger/ToolSurface/PropertyEngine/Seat/SUT/Oracle/Evidence） | 数据（一个 World 实例 + 声明的事实 + 敞开的注入面 + 绑定的属性） |
| 知不知道机密 | **永远不知道** | 声明什么算机密、谁有权、什么算出事 |
| 变更方式 | 钉死后尽量不动 | 随时加，**加数据不改内核** |

**最高约束：加场景 = 加数据，不改内核。** 平台性来自内核通用，不来自一次建很多东西。

### 允许 / 禁止（内核侧）

| 行为 | 状态 |
|---|---|
| 新增域/角色/数据/注入面/属性，仅通过场景数据 | 允许 |
| 为某场景在内核里加 `if scenario == X` 分支 | 禁止 |
| 把某场景的机密/攻击写进内核默认值 | 禁止 |
| 新增间接注入时写死工具调用序列（`execution.steps` 式） | 禁止 |
| 良性对照与攻击共享 world + 中性 task，只切 inject | 要求 |

## 2. 靶场 vs XA-Guard（被测防护）

靶场是独立平台。它可以**评测** XA-Guard，但**不能依赖** XA-Guard 内部实现。XA-Guard 只是"guard 模式"下的一个 SUT。

| 行为 | 状态 |
|---|---|
| 通过命令行启动外部 SUT（`python -m xa_guard.server --config <生成 yaml>`） | 允许 |
| 通过 MCP stdio / MCP HTTP / HTTP 调用外部 SUT | 允许 |
| 读取外部 SUT 落盘审计（Gate6）作为证据 | 允许 |
| 把 XA-Guard 当 `sut_mode=guard`、把直通当 `sut_mode=null` | 允许 |
| `import xa_guard` 或复用其 helper | **禁止** |
| 修改 XA-Guard 策略/测试来迎合靶场 | **禁止** |
| 把靶场 runtime 放进被测产品根 `src/` | **禁止** |

> 靶场只按场景/席位生成**临时** Gate3/Gate4 配置喂给外部 SUT（复用 `policy_overlay`/`sut_xaguard` 的做法），生成物属于证据，不属于 XA-Guard 源码。

## 3. Mock 系统原则

Mock 工具**不预置安全拦截**。它们只执行合成业务动作、记录本地副作用并落账。
是否该 allow/deny 由 SUT 与 Oracle 共同验证——否则 Null 基线会被虚假加固，防护增量就测不出来了。

## 4. 账本中立

账本只如实记事实（谁/身份/工具/数据/接收方/裁决），**不判断攻击、不分类攻击、不反推 SUT 策略**。
判据在 PropertyEngine，裁决在 SUT，verdict 在 Oracle——三者都只读账本与世界事实。

## 5. 红线（继承 PRD §7 + operator-guide）

- 不做真实外发、不用真实凭据/生产数据、不攻击公网目标、不执行真实破坏性命令。
- SECRET 只允许不可用样本；SECRET 出现在 agent 工具入参 = 配置缺陷。
- 人工观察/smoke/INFRA_ERROR 不混入自动化统计口径（见 evidence-and-accountability）。
