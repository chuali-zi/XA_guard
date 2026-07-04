# SP5 多 Agent 与追责设计

> 状态：设计草案，待作者审后进实现。依赖 SP1–SP4。
> 追责三链见 [../architecture/ledger-schema.md](../architecture/ledger-schema.md) §4，追责模型见 [../architecture/evidence-and-accountability.md](../architecture/evidence-and-accountability.md) §5。

## 目标

把靶场从"单 seat 攻关"深化到"多 agent 协作 + 委托"，并落地本产品的灵魂——**从坏地面真值状态点名元凶**，
再用反事实对照（null vs guard）证明防护把"黑盒混乱"变成"可裁决、可追责"。

## 边界

- 三链是数据，写进账本；追责引擎只读账本，不反推 SUT 策略。
- 不做真实外发/凭据；委托/审批票据全 synthetic。

## 模型

- **多 seat 编排**：一次 attempt 可涉及多个域/级别的 seat（如 F3 员工→主管→财务、F11 跨部门三向）。
- **委托**：跨域/跨 seat 委托的每一跳写 `delegation_chain`（含 approval_ticket）；特权动作须 MFA/审批。
- **身份链**：`identity_chain` 保留 `original_principal`，禁止非本 seat 伪造/继承身份（防 AT7）。
- **追责引擎**：从 Property 报出的 Violation 关联账本 entry，沿三链回溯 →
  - 链完整 → 输出"最初主体 + 经谁授权 + 由谁代劳"。
  - 链断裂 → 输出"有害后果无法被追责"（本身即一种赢，PRD §5）。
- **反事实**：同场景 null vs guard 两份账本对照，量化防护增量。

## 判据

一条多跳委托导致的泄漏，能从账本三链**唯一地**追到担责主体；若链被伪造/断裂，追责引擎如实报"不可追责"。

## 验收

```
构造一条跨 seat 委托的泄漏竖切（红队 finding），guard/null 各跑：
- null：泄漏发生，追责引擎从账本给出元凶链（或报链断裂）。
- guard：被拦，账本一条链清晰；反事实对照给出 ASR_null−ASR_guard>0、leak 从 >0 到 0。
```

## 后续

- 把追责链 + 反事实喂给 SP6 的现场对照 demo 与看板。
- 更复杂的委托拓扑（多跳、环、跨域）作为红队高级素材。
