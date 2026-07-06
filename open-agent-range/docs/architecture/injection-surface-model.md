# 注入面模型 — 通用"多角度投毒"

> 层级：架构约定（跨 SP）。本文把 arena 现在只有的 `mailbox:` 注入泛化为**通用注入目标分类**，落地 PRD"从任意角度、任意组合投毒"。
> 本文只描述**注入面在哪里、内核怎么处理**；**不写任何 payload、不写任何机密**（那是场景 fixtures/红队 finding）。

## 1. 核心原则

- **注入 = 把数据放进世界状态，不是脚本。** 内核把红队 payload 当作"世界里本就会流动的内容"（一封邮件、一段日志、一篇被检索的文档、一个插件清单…）注入到某个世界位置；agent 之后如何反应，是它自己的自由，内核**绝不预置工具调用序列**。
- **良性对照与攻击共享 world + 中性 task，只切 inject。** 这样 A/B（null vs guard）只有"有没有注入"这一个变量。
- **判据与注入解耦。** 抓不抓得住由 PropertyEngine 的属性决定（读账本坏状态），与"攻击从哪个面来"无关。

注入自由分三层，三层缺一不可：

| 层 | 含义 | 不达标表现 |
|---|---|---|
| Placement | 任意 `scheme:locator` 可落到世界并留证 | 新 scheme 被拒绝或需要改场景专用代码 |
| Consumption | 现实会被读/处理的入口会被 seat 消耗 | payload 只躺在 `domain_state`，没有 seat/工具会碰它 |
| Consequence | 消耗后可能改变工具面、权限、供应链、审计或副作用 | 所有攻击都退化成"读文本后外发"一条路 |

当前竖切可以先证明 Placement 和部分 Consumption；产品完成态见
[../specs/SP7-product-completion-spec.md](../specs/SP7-product-completion-spec.md)，必须覆盖语义型 Consequence。

## 2. 注入目标分类（InjectionTarget）

注入目标用 `scheme:locator` 表示，内核按 scheme 把内容落到对应世界位置：

| scheme | 落到世界的哪里 | 一天中的触点（示例语境，非题目） | 主要攻击类目 |
|---|---|---|---|
| `mailbox:` | 某 principal 的邮箱 | 晨间查邮件、甲方需求邮件、内部通知 | AT2 间接注入、AT3 外泄、AT5 审批绕过 |
| `rag:` / `doc:` | 被检索的知识库/文档/会议纪要 | 方案检索、政策查询、会议纪要 | AT2 间接注入、AT6 任务链偏离 |
| `log:` | 运维/应用日志 | 运维查日志排障 | AT2、AT4 工具越权 |
| `plugin:` / `mcp:` | 插件/MCP 工具清单与说明 | 研发装插件、扩展工具面 | AT8 供应链、AT4 越权 |
| `ticket:` | 工单/需求单 | 工单三角化、变更单 | AT2、AT6 |
| `supply:` / `aibom:` | 制品/依赖/AIBOM 声明 | 研发拉依赖、发布制品 | AT8 供应链、AT10 声明漂移 |
| `insider:` | 一个"内鬼" seat 的行为 | 越权员工、被攻陷席位 | AT7 多 agent 委托、AT4、AT11 策略例外滥用 |
| `meeting:` | 会议纪要/日程 | 晨会、跨部门评审 | AT2、AT6 |
| `policy:` | 被引用的策略/手册文本 | 治理策略引用 | AT2、AT11 |

> 分类**开放不封闭**：现实里能被攻击的地方都要能被建成一个注入面。新增注入面 = 加一个 scheme handler（内核）+ 场景在该面敞开（数据），仍不脚本化攻击。

`plugin:`/`mcp:`、`supply:`/`aibom:`、`insider:` 是语义型注入面：它们不应被强行建成普通 `read_*`
文本读取，而应分别改变工具面、制品/依赖事实、seat 行为或授权状态。否则会让"自由注入"只停留在落位层。

## 3. 注入 API（内核形态）

```
apply_injections(world, injections) -> world      # injections: list[{into: "scheme:locator", fixture: <payload 引用>}]
```

- 内核按 `into` 的 scheme 分发到对应 handler，把 `fixture` 内容放进世界状态的那个位置。
- `fixture` 只是"世界里的一段内容"引用，内核不解读其意图、不据此分支。
- 组合投毒 = 多条 injection 落到多个面；内核一视同仁当世界数据。

> arena `injection.py` 目前只实现 `mailbox:`（且 handler 里对 subject/sender 有 office 假设）。SP3 的任务就是把它泛化成上表的多 scheme 分发，并去掉 office 专用假设。

## 4. 攻击类目对照（AT1–AT12）

注入面是"入口"，攻击类目是"目的/手法"。完整类目见 [../reference/attack-surface.md](../reference/attack-surface.md)：
AT1 直接输入、AT2 间接污染、AT3 数据外泄、AT4 工具越权、AT5 审批绕过、AT6 任务链偏离、
AT7 多 Agent 委托、AT8 供应链、AT9 沙箱隔离、AT10 审计完整性、AT11 策略例外滥用、AT12 评测逃逸。

## 5. 内核不做什么

- 不预置 payload、不预置机密、不预置"攻击会怎么展开"。
- 不按注入面给判据开后门（判据只读账本坏状态）。
- 不把"某注入面 → 某工具序列"写死进内核。
