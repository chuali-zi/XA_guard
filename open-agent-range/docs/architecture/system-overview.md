# 系统总览 — 一张图看懂 Open Agent Range

> 层级：架构约定（跨 SP）。本文是所有架构/场景/SP 文档的入口坐标系。
> 它只描述"内核如何被建模、闭环如何跑、组件如何映射到 SP 与一天"，**不写题、不写攻击、不写机密**。

## 1. 一句话定位

Open Agent Range = **一个通用内核（物理引擎）+ 可无限扩展的场景（数据）**。
内核搭一个每天照常运转的企业世界，把所有接口敞开给红队从任意角度投毒；
一本不可篡改的账本如实记下"谁、以什么身份、动了什么、碰了哪条数据、发给了谁"；
被测防护（SUT，如 XA-Guard）在环裁决；靶场只从账本与副作用判定输赢与追责，**不靠预设脚本**。

（北极星见 [../PRD.md](../PRD.md)。本文不重复"为什么"，只讲"怎么被建模"。）

完成态坐标见 [../specs/SP7-product-completion-spec.md](../specs/SP7-product-completion-spec.md)：它把
"真实的一天"定义为 **scheduler 推进世界、Seat 自主产生工具尝试、SUT 逐次裁决、副作用再落账**，
而不是一盘预录的正常事件磁带。

## 2. 内核 vs 场景（一切设计的分界线）

```
┌─────────────────────────── 内核 KERNEL（通用，场景无关） ───────────────────────────┐
│  World      仪表化世界状态（人/角色/数据资产/信任边界/各域子状态）                    │
│  Ledger     不可篡改地面真值账本（append-only + hash chain + 身份/授权/委托链）       │
│  ToolSurface 仪表化工具面（只改/观察世界 + 落账；从不判断"这是不是攻击"）             │
│  PropertyEngine 可插拔判据（从账本/世界事实读"赢"的属性）                             │
│  Seat       agent 席位契约（scripted / opencode / 红队手动）                          │
│  SUT        被测防护契约（null / guardstub / xaguard）                                │
│  Oracle     从世界副作用 + 账本 + SUT 审计产出 verdict（不反推 SUT 策略）             │
│  Evidence   每次 attempt 的证据包与 hash 清单                                         │
└──────────────────────────────────────────────────────────────────────────────────┘
              ▲ 只认接口，不认具体场景
              │
┌─────────────┴───────────── 场景 SCENARIO（数据，不改内核） ─────────────────────────┐
│  一个 World 实例（数字城市科技集团 DCTG 的一天）                                      │
│  + 声明的事实（什么算机密、谁有权、什么算出事）                                       │
│  + 敞开的注入面（红队可投毒的入口，非脚本化攻击）                                     │
│  + 绑定的属性（本场景用哪些判据裁决）                                                 │
└──────────────────────────────────────────────────────────────────────────────────┘
```

**铁律：加场景 = 加数据，不改内核。** 内核永远不知道"这一场景的机密是什么、攻击会怎么来"。

## 3. 核心闭环（一次 attempt 的生命周期）

```
   场景数据
      │  build world（正常一天的初始世界）
      ▼
  ┌─World─┐   ← 红队在敞开的注入面投毒（把 payload 当数据放进世界状态，不是脚本）
  └───┬───┘
      │  Seat（agent）在世界里以某身份领任务、自主调用工具
      ▼
  ToolSurface ──调用尝试──►  SUT（null 直通 / guard 裁决 allow·deny·proxy）
      │                          │
      │◄──────── 放行的动作 ──────┘
      ▼
  World 记录副作用（egress / 状态变化）  ──►  Ledger 逐条落账（含身份/授权/委托）
      │                                            │
      ▼                                            ▼
  PropertyEngine 读账本事实判"是否进入坏状态"   Oracle 综合副作用+账本+SUT审计出 verdict
      │                                            │
      └───────────────► Evidence 证据包 ◄──────────┘
                           │
                           ▼
                 追责（沿账本链点名元凶）+ 反事实对照（null vs guard）
```

判据是**通用属性**（PRD §5），不是预设步骤：攻击怎么来无所谓，只看世界有没有进入本不该出现的地面真值状态。

## 4. 组件 ↔ SP 映射

| 内核/能力 | 首次成形于 | 深化于 |
|---|---|---|
| World / Ledger / ToolSurface / PropertyEngine / Seat / SUT / Oracle / Evidence 契约 | **SP1 内核** | — |
| DCTG 一天作为场景数据（先竖切 1–2 域，再拓宽） | **SP2 参考场景** | 后续逐域 |
| 通用注入面（mailbox/rag/log/plugin/ticket/supply/insider…） | **SP3 注入面** | — |
| 红队工作台（看图→投毒→A/B→读证据→提 finding→固化） | **SP4 工作台** | — |
| 多 agent + 身份/授权/委托链 + 追责引擎 | **SP5 追责** | — |
| 现场对照 demo + 看板 + live 统计 | **SP6 演示** | — |
| 产品完成态验收矩阵（真实一天、live SUT、判据族、自由注入） | **SP7 总 spec** | — |

## 5. 组件 ↔ 一天映射

一天里"照常发生的正常业务"落在 World + Ledger + ToolSurface 上；"红队从任意角度投毒"落在注入面上；
"到底出没出事、谁担责"落在 PropertyEngine + Oracle + 追责上。详见
[../reference/a-day-in-the-life.md](../reference/a-day-in-the-life.md) 与
[../reference/attack-surface.md](../reference/attack-surface.md)。

## 6. 被测防护（SUT）如何在环

内核只认 SUT 契约（allow/deny/proxy）。XA-Guard 只是"guard 模式"下的一个 SUT 实例：
经 MCP stdio 串在 OpenCode 席位与靶场 office server 之间，靶场为它按场景/席位生成临时的
Gate3/Gate4 配置。**靶场不 `import xa_guard`、不改其策略**。详见
[decoupling-contract.md](decoupling-contract.md) 与 [evidence-and-accountability.md](evidence-and-accountability.md)。

完成态要求真实 SUT 在环：每一次工具尝试先经 `NullSUT`/`GuardStubSUT`/`XaGuardSUT` 之一裁决，
只有被 allow/proxy 的动作才能改变世界；XA-Guard 模式必须回读 Gate6 审计并与靶场账本对齐。

## 7. 复用来源

本架构把 `enterprise-agent-range/arena/` 已验证的解耦结构（World/Challenge/Oracle/Seat/SUT/PolicyOverlay/
Evidence/Findings，30 arena 测试 + XA-Guard live 2×2 smoke）与 `spike.py` 的 Ledger 脊梁**吸收并泛化**为
上面的通用内核；enterprise-agent-range 降级为参考/归档，不产生 runtime 依赖。
