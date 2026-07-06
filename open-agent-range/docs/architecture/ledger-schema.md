# 账本 Schema — 不可篡改的地面真值账本

> 层级：架构约定（跨 SP）。账本是内核的**脊梁**：既是安全判据的唯一真相源，也是追责的证据。
> 本文定义 entry schema、hash chain、身份/授权/委托链与持久化；**不写具体机密**（机密是场景数据）。

## 1. 为什么是脊梁

PRD 要的不是"拦没拦住"，而是"到底出了什么事、该谁负责，能如实查清"。所以每一次世界副作用与关键决策，
都必须落成一条**不可篡改、可重放、可追责**的事实。判据从账本读（通用属性），追责沿账本链走（点名元凶）。

## 2. Entry Schema

每条 entry 是一次"谁、以什么身份、动了什么工具、碰了哪条数据、发给了谁、被谁怎么裁决"的事实：

| 字段 | 含义 | 备注 |
|---|---|---|
| `seq` | 单调递增序号 | 从 1 起 |
| `ts` | 逻辑时钟（业务时钟刻度） | 见 a-day-in-the-life 的世界时钟 |
| `actor` | 实际发起者显示名 | 如"林工" |
| `principal` | 规范身份 | 如 `office.default.7@dctg.local` |
| `seat` | agent 席位 ID + 级别 | 如 `office.default.7` (L1) |
| `role` | 角色 | 员工/领导/财务/运维/技术/审计… |
| `action` | 动作语义 | read_record / submit / approve / pay / send … |
| `tool` | 实际调用的工具名 | 对应 ToolSurface 的 `ToolDefinition.name` |
| `data_ref` | 碰到的数据资产 ID | 只存引用，不存机密内容明文 |
| `classification` | 该数据分级 | PUBLIC/INTERNAL/CONFIDENTIAL/SECRET |
| `to` | 接收方 | 内部 principal 或外部 receiver |
| `external` | `to` 是否越过信任边界 | 由 `is_external` 判定 |
| `decision` | SUT 对本动作的裁决 | allow/deny/proxy/null |
| `identity_chain` | 身份链 | 见 §4 |
| `authorization_chain` | 授权链 | 见 §4 |
| `delegation_chain` | 委托链 | 见 §4 |
| `prev_hash` | 前一条的 hash | 首条为 null |
| `hash` | 本条规范化后的 sha256 | 见 §3 |

> `data_ref` 只存资产 ID + 分级，**不落机密明文**。若某工具入参里出现 SECRET 明文，这本身就是配置缺陷（见 data-classification）。

## 3. Hash Chain（不可篡改）

- 规范化：对 entry（含除 `hash` 外全部字段）做 `json.dumps(..., ensure_ascii=False, sort_keys=True, separators=(",",":"))`，取 sha256。
- 链接：`entry.prev_hash = 前一条.hash`，首条 `prev_hash = null`。
- 校验 `verify_hash_chain()`：逐条重算 hash、核对 `prev_hash` 衔接；任一处不符即判定篡改（对应 attack-surface 的 AT10 审计完整性攻击）。

> 复用 spike `Ledger._hash` / `verify_hash_chain` 的做法；本内核把它从内存 spike 升级为持久化脊梁。

## 4. 身份 / 授权 / 委托链（追责三链）

追责的关键是能沿链回答"这条有害后果，最初是谁、经谁批、由谁代劳"：

- **identity_chain**：真实主体 → agent 席位 → 实际执行身份。防"身份冒用/继承"（保留 `original_principal`，禁止非本 seat 伪造或继承他人身份）。
- **authorization_chain**：该动作依据哪条授权/审批放行。特权动作须能指到 `approval_ticket`。
- **delegation_chain**：跨域/跨 seat 委托的每一跳，形如：

```json
[
  {"principal": "alice@dctg.local", "role": "L1"},
  {"principal": "bob@dctg.local",   "role": "L2", "approval_ticket": "APPR-…"}
]
```

链断裂（有害后果找不到担责主体）本身就是一种"赢"（PRD §5 的 unattributable-harm）。

> 链字段与 enterprise-seat-plan 的委托约束、`fixtures/audit/delegation-trace.json`/`approval-tokens.json` 对齐。

## 5. 持久化

- 形态：**append-only JSONL**，一行一条 entry，落盘即成证据。
- 只追加、不回改；任何"修改历史"必须表现为篡改并被 `verify_hash_chain` 抓到（供 AT10 类攻击验证）。
- 每次 attempt 的账本随证据包归档（见 evidence-and-accountability 的 `ledger`/`artifact-hashes`）。

## 6. 重放与取证

- **重放**：按 `seq` 顺序重演可复现世界终态与判据结果，用于回归与"这次到底发生了什么"的复盘。
- **取证**：审计域（Audit）的 seat 可 `verify_chain` / `replay_trace` / `export_evidence`（只读），产出可对照的证据包。
- 反事实：同一场景 null vs guard 两份账本对照，量化"防护把黑盒混乱变成可裁决可追责"的增量（见 evidence-and-accountability §metrics）。

当前实现进度：

- `Ledger.replay(world)` 已实现 `ledger_projection_v1`：从账本事实重建 egress、tool attempt、SUT decision、ticket/approval/CI/audit 队列投影、服务/插件/注册表变化索引，并写入证据包 `ledger-replay.json`。
- 关键参考工具已把不含机密明文的 replay metadata 纳入 ledger entry；full-day 证据包当前可从账本复原 `build-77=succeeded`、`gateway=healthy`、审计包 `EVIDENCE-DAILY=exported` 等终态。
- 该投影只读取账本，不读取 prompt 或机密明文；hash chain 断裂时会在 replay 中明确暴露。
- 仍未完成完整世界级 replay：更多工具/动态工具的 state payload 覆盖、Gate6 audit 与 range ledger 的 hash/seq 对齐、report/replay CLI 仍待补。

## 7. 内核不做什么

- 账本不判断攻击、不分类攻击；它只如实记事实。判据是 PropertyEngine 的事，裁决是 SUT 的事。
- 账本不存机密明文，只存引用 + 分级。
