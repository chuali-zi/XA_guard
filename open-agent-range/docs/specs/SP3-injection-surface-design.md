# SP3 注入面设计 — 通用"任意角度投毒"

> 状态：设计草案，待作者审后进实现。依赖 SP1 内核、SP2 场景。
> 模型见 [../architecture/injection-surface-model.md](../architecture/injection-surface-model.md) 与 [../reference/attack-surface.md](../reference/attack-surface.md)。

## 目标

把注入目标从 arena 现有的仅 `mailbox:` 泛化为**通用注入面全谱**，让红队能从一天里的任意入口、任意组合投毒，
且内核始终把注入当作"放进世界状态的数据"，绝不脚本化。

完成态不只要求"能放进去"，还要求现实会处理这些入口的 seat/工具会消费它，并且消费后能造成对应类型的世界后果：
文本入口可能影响外发，工具/供应链入口可能改变工具面或制品事实，insider 入口可能改变行为主体与追责链。

## 边界

- 注入 = 数据落位，不是工具序列；内核不据 payload 意图分支。
- payload/机密只存在于 fixtures / 红队 finding，不进内核、不进文档。
- 判据与注入解耦：抓不抓得住由属性决定，与注入面无关。

## 模型

- **scheme handlers**：`mailbox: / rag:|doc: / log: / plugin:|mcp: / ticket: / supply:|aibom: / policy: / meeting: / insider:`，每个把 `fixture` 内容落到对应世界位置（泛化 arena `injection.py`，去掉 office 专用假设）。
- **注入 API**：`apply_injections(world, injections)`，按 `into` 的 scheme 分发；多条 = 组合投毒。
- **良性对照**：共享 world + 中性 task，只切 inject（有/无、哪几面）。
- **insider:**：以一个"内鬼/被攻陷 seat"的行为作为注入，接 SP5 的多 agent。

### 三层验收

| 层 | 本 SP 要证明什么 |
|---|---|
| Placement | 所有已知 scheme + 未登记 scheme 都可落位并留证 |
| Consumption | mailbox/rag/doc/log/ticket/policy/meeting 等内容型入口可被 seat 读取；plugin/mcp/supply/aibom/insider 进入后续语义消费路径 |
| Consequence | 注入不只触发敏感外发，也能触发工具面漂移、审批绕过、供应链漂移、审计断链、委托/身份混淆等属性 |
 
`plugin:`/`mcp:` 的完成形态是工具面漂移：污染工具描述、schema、capability、risk、taint、origin 或签名状态。
`supply:`/`aibom:` 的完成形态是制品/依赖声明漂移。`insider:` 的完成形态是 seat 行为或授权状态变化。

## 判据

同一 world 挂多个注入面时，内核对每个面一视同仁当数据；无任何 `if scheme == X: 调用某工具` 的分支。

## 验收

```
对同一 world 分别从 mailbox/rag/log/plugin/ticket/supply 注入良性 fixture，正常一天仍零违规。
注入可触发坏状态的 fixture 时，对应属性识别；kernel 无 scheme 意图分支（代码审查 + grep 证明）。
至少一个非文本语义型注入面（plugin/mcp/supply/aibom/insider）能改变 world/tool surface/accountability，并影响 null vs guard 裁决。
```

## 后续

- 注入面接入红队工作台（SP4）的 `init-finding --target scheme:locator`。
- 组合投毒（多面）作为 SP5 多 agent/委托攻击的素材。
