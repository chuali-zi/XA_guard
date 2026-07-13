# Agent Identity 与 Undo 可行性设计

> 状态：**PROPOSED DESIGN / FEASIBILITY GO / NOT DELIVERED**
> 日期：2026-07-12
> 交付口径仍以 [`docs/acceptance/DELIVERY-v2.md`](../acceptance/DELIVERY-v2.md) 为准。本文不改变比赛主叙事，也不表示 XA-Guard 已具备生产 IAM 或通用 Undo。

## 1. 决策摘要

建议保留两个方向，但先用最小竖切验证，不直接进入正式产品改造：

1. **可信双主体身份**：一次工具调用必须能回答“哪个人委托了哪个 Agent”。人类主体与 Agent 工作负载主体都应来自可验证凭据，而不是来自调用参数中的自报字符串。
2. **动作级恢复**：Undo 不是时间倒流，而是依据工具契约执行恢复、补偿或止损。原动作和补偿动作都必须保留，不能删除原始审计事实。

比赛定位暂不调整。若竖切通过，后续建议把身份作为 Agent Gateway 主线，把 Undo 作为 AI Resilience 亮点；若竖切不通过，则保留为研究设计，不进入交付承诺。

## 2. 当前仓库事实

### 2.1 已有身份治理

- Governance registry v0.2 已包含 tenant、principal、role、role binding、Agent inventory、data domain、预算与审批策略。
- `GovernanceEnforcer` 已能在 Gate1 前进行 principal-Agent-tool-data-domain 联合预检，并把结果写入 Gate6。
- 当前可信边界不足：`_xa_guard.human_principal`、`agent_id`、`tenant_id` 由调用者自报；`capability_token` 只生成安全摘要，没有验签。
- 因此当前能力是“静态治理语义原型”，不是身份认证系统，也不能证明调用者确实拥有所声明身份。

### 2.2 已有恢复基础

- Gate6 提供 append-only hash chain 审计，OAR ledger 可重放关键世界投影。
- pending approval 能在重启后恢复待审批请求，但它恢复的是“尚未执行的请求”，不是已发生业务副作用的 Undo。
- OAR 的 `update_registry`、`modify_policy`、`manage_ci`、`pay`、`send_message` 等工具会改变世界或产生外发副作用，目前没有统一可逆性契约和补偿状态机。

## 3. 目标模型

### 3.1 身份模型

可信上下文至少包含：

| 字段 | 含义 | 可信来源 |
|---|---|---|
| `sub` | 发起任务的人类主体 | 经过验签的委派凭据 |
| `act.sub` | 实际执行任务的 Agent 主体 | 经过验签的工作负载/委派凭据 |
| `tenant_id` | 组织边界 | 签名 claims 与 registry 交集 |
| `aud` | 目标 XA-Guard 实例 | 严格 audience 校验 |
| `tools` / `data_domains` | 本任务的能力上限 | 短期签名 claims |
| `task_id` / `jti` / `exp` | 任务、凭据与期限 | 短期签名 claims |

授权结果取“签名 claims 允许范围”和“Governance registry 允许范围”的交集。凭据只能缩权，不能给 registry 中不存在的权限扩权。

`_xa_guard` 中的未签名字段仍可描述本次请求访问的数据域、资源对象和成本估算，但不能覆盖已验证的 `sub`、`act.sub` 或 tenant。二者冲突时必须 fail closed。

### 3.2 正式工程候选接口

若实验通过，正式实现再考虑：

- HTTP：按 MCP Authorization 把 XA-Guard 做成 OAuth resource server，验证 Bearer token、issuer、audience、scope 和 JWKS。
- stdio：从进程环境读取 Agent 工作负载凭据；多用户委派可携带短期签名 assertion，并要求 `act.sub` 与工作负载身份一致。
- registry：Agent 增加 workload identity 绑定，role permission 增加查看 effect、申请 Undo、批准 Undo 等动作。
- Gate6：只记录 issuer、kid、claims 摘要和验签结果，永不记录原始 token。

上述均为候选设计，不属于本次最小实验实现。

## 4. Undo 语义

| 类型 | 定义 | 示例 | 行为 |
|---|---|---|---|
| `reversible` | 能恢复原对象前态 | registry/policy 字段更新 | 捕获前态后执行反向更新 |
| `compensatable` | 不能抹除原动作，但可产生反向业务动作 | 支付后的退款、插件发布后的下架 | 追加 refund/yank 等新事实 |
| `irreversible` | 无可靠通用反向动作 | 已送达外部的消息、已泄漏数据 | 拒绝伪 Undo，返回止损/人工处置 |

正式工具契约候选字段为 `side_effect_level`、`reversibility`、`prepare_tool`、`undo_tool`、`undo_window_seconds`、`compensation_hint` 和 `irreversible_warning`。MCP ToolAnnotations 只能作为提示，不能代替 XA-Guard 本地可信契约。

补偿事务必须满足：

- 原动作前捕获最小必要前态；捕获失败时不执行原动作。
- 原动作与补偿动作分别经过身份、治理、Gate3、Gate5 和 Gate6。
- 原审计记录不可修改或删除；补偿通过新 trace 关联原 effect。
- 补偿处理器必须幂等，可识别已完成、失败和过期状态。
- 高风险、跨主体、策略、权限和资金类补偿必须实行职责分离。

## 5. 本次实验范围

实验只验证最短闭环：

- 在内存中生成 Ed25519 临时密钥，签发实验性 compact JWS。
- 真实 `Pipeline + GovernanceEnforcer + Gate6` 验证身份通过/拒绝和下游零执行。
- 真实 OAR `ToolSurface + World + Ledger` 执行一次 `update_registry`，捕获前态并由第二个签名主体恢复。
- 对 `send_message` 给出不可逆对照，证明系统不会伪造恢复能力。
- 生成独立 evidence，验证 XA-Guard audit chain、OAR ledger chain、状态恢复和 token 不落盘。

本次不实现真实 IdP、远程 JWKS、正式 HTTP/stdio 中间件、加密 SQLite、重启恢复、并发控制、通用补偿 DSL、生产 UI 或正式 MCP Undo 工具。

## 6. Go / Conditional / No-Go

- **GO**：身份伪造全部 fail closed 且下游零执行；可逆动作恢复前态；原/补偿审计均保留；不可逆动作如实拒绝；两条 hash chain 均通过。
- **CONDITIONAL**：概念成立，但接入必须修改正式 Pipeline、下游工具契约或审计 schema；必须先列明侵入点再评审。
- **NO-GO**：无法可靠绑定人类与 Agent，或无法在不破坏审计真实性的前提下恢复动作。

## 7. 安全与合规边界

- 实验私钥只存在于进程内，不写入仓库或 evidence。
- evidence 只使用合成身份和合成业务状态。
- 不把实验签名器表述为生产 OIDC/JWKS 实现。
- 不把 OAR 世界恢复表述为真实业务系统通用回滚。
- 新增依赖前必须确认许可证并进入 AIBOM；本实验复用现有 `cryptography` extra，不增加依赖。

## 8. 2026-07-12 实验结果

最小竖切结论为 **GO（仅代表进入下一阶段具备可行性）**，证据见
[`docs/evidence/agent-identity-undo-spike-2026-07-12/`](../evidence/agent-identity-undo-spike-2026-07-12/)：

- 坏签名、过期、错误 audience、自报身份冲突四类负测全部 deny，拒绝阶段 executor 调用数为 0。
- 合法 Alice + `open-agent-range` 双主体凭据完成 `update_registry`；Alice 自批 Undo 被职责分离拒绝，Carol 补偿产生独立 trace，目标 registry entry 恢复到原值。
- `send_message` 被记录为 `irreversible`，Undo 只产生 `manual_required`，没有伪造召回或删除原事实。
- Gate6 audit chain、OAR ledger chain、状态恢复、trace 分离和原始 token 不落盘全部通过。
- 相关 51 项身份/治理/审批/OAR 基线测试与 3 项新增实验测试通过；实验测试连续重复 5 轮均通过。

实验同时暴露两个工程事实：

1. 首次运行没有登记 `update_registry` 的 Gate4 capability，真实 Pipeline 按未知外联工具 fail closed；因此正式实现必须把身份与可信工具/副作用契约一起设计。
2. 初版坏签名构造只替换 Base64URL 尾字符，可能只改变未使用填充位；现改为翻转实际签名字节，并用五轮重复测试验证负测稳定性。

GO 不覆盖真实 IdP/JWKS、MCP 传输认证、加密持久化、重启恢复、并发 Saga 或真实业务连接器。
