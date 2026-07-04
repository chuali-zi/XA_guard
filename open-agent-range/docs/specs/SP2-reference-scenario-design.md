# SP2 参考场景设计 — DCTG 的一天（数据化）

> 状态：设计草案，待作者审后进实现。依赖 SP1 内核。
> 世界蓝图见 [../reference/enterprise-world.md](../reference/enterprise-world.md) 与 [../reference/a-day-in-the-life.md](../reference/a-day-in-the-life.md)。

## 目标

把数字城市科技集团的"一天"实现为**场景数据 + fixtures**，证明 SP1 内核**真的通用**：
加一个域 = 加数据、不改内核。先竖切 1–2 域跑通，再逐域拓宽。

## 边界

- 场景是数据：world 实例 + 声明事实 + 敞开注入面 + 绑定属性，全部落 fixtures/scenario，不改内核。
- 不写题、不写攻击、不写机密明文；良性对照与攻击共享 world + 中性 task，只切 inject（无 `execution.steps`）。
- 本 SP 不做通用注入面全谱（SP3 只需支持本竖切用到的面）、不做工作台/看板。

## 模型

### 场景 schema（数据）

```
scenario/
├── world.json           # DCTG world 实例：principals / data_assets(带分级) / sinks / domain_state
├── normal-day.json      # 正常业务流事件（a-day-in-the-life 的机器可读版，仅正常业务）
├── surfaces.json        # 本场景敞开的注入面（scheme:locator 列表，非 payload）
├── properties.json      # 本场景绑定的属性集及参数（sensitive_markers 等）
└── fixtures/            # data/mail/rag/plugins/ops_logs/policies/audit（见 data-classification §4）
```

### 首个竖切（SP2.0）

- 域：**Office + Business Data**（复用已跑通的 office/mail + 一个数据域）。
- 席位：`office.default`(L1)、`office.manager`(L2)、`biz.power`(L2)。
- 正常流：F1/F3/F4/F6/F15（查邮件、报销审批链、甲方需求→方案、数据查询、外发点）。
- 注入面：`mailbox:`、`rag:`/`doc:`（本竖切够用）。
- 绑定属性：sensitive-egress（CONFIDENTIAL+ 到 external）+ unattributable-harm。

### 逐域拓宽（SP2.1+）

按 [../reference/expansion-roadmap.md](../reference/expansion-roadmap.md)：Ops(`log:`) → Dev(`plugin:/supply:`) → Governance(`policy:`) → Audit(AT10)。
每接一个域：加该域 world 子状态 + 工具面 + fixtures + 绑定属性 + 良性对照，**不改内核**。

## 判据

- 正常一天（无注入）：账本干净、零违规、hash 链完整。
- 有注入的攻击竖切：坏状态被绑定属性识别；良性对照在 guard/null 两路都通过。

## 验收

```
python -m kernel.run --scenario scenario/ --agent scripted            # 正常一天，零违规
python -m kernel.run --scenario scenario/ --agent scripted --probe    # 竖切属性能识别坏状态
# 通用性证明
接入第二个域仅新增 scenario 数据与 fixtures，kernel/ 代码零改动（diff 证明）
```

预期：内核 + DCTG 场景能跑（竖切的）一天；"加一个域 = 加数据、不改内核"由 diff 证明。

## 后续

- 把每个域的良性对照与 smoke 证据固化，作为红队工作台（SP4）的基线 world。
- 真实 agent live（OpenCodeSeat + XaGuardSUT）跑竖切 A/B（授权后）。
