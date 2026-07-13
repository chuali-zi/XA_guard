# 仓库状态：XA-Guard / XA-202620

> 快照日期：**2026-07-12**（America/Los_Angeles）
> 当前统一口径：**CORE-IMPLEMENTED / DEPLOYMENT-PENDING**
> 比赛交付口径：[docs/acceptance/DELIVERY-v2.md](docs/acceptance/DELIVERY-v2.md)
> 本文件只描述当前状态；工作历史见 [log.md](log.md)。

## 总体结论

XA-Guard 六关、OAR 主评测和新 Identity + Undo 核心代码均已实现。Reference Compose 已从空 PostgreSQL volume 一键构建启动，并通过真实 Keycloak Authorization Code + PKCE、Standard Token Exchange V2、Alice 创建工单、Alice 自批拒绝、Dora 独立批准、Worker 补偿、业务 `open -> cancelled` 的协议级闭环。

当前仍**不是** `REFERENCE-READY`，也不是 `HA-READY`：交互式浏览器三账号人工 UI 验收、完整故障注入/身份负测/并发性能和 kind 多副本验收尚未封存。Delivery v2 的 B6/B7 因此保持 `PARTIAL`，不得改写为生产 IAM、绝对 exactly-once 或通用数据库 Undo 已落地。

## 当前能力状态

| 能力面 | 状态 | 当前事实与边界 |
|---|---|---|
| Gate1–6 与 Gate6 审计 | `DONE` | 既有 MCP/demo/OAR 路径保留；新原动作和补偿也进入相同 Pipeline |
| OAR B1–B5 主证据 | `DONE` | canonical Null vs XA-Guard A/B、ledger replay 与 audit 对齐保持原状态 |
| Keycloak/OIDC 身份 | `CORE-IMPLEMENTED` | discovery/JWKS 启动必需；普通离线验签；敏感接口 introspection；`act.sub` 优先、Keycloak `azp` reference 映射；未知 kid 有刷新、负缓存和节流 |
| 动态 Agent assignment | `CORE-IMPLEMENTED` | PostgreSQL human/group→Agent→tool/data-domain，有效期/版本/变更人；每次调用与 YAML ceiling 相交，撤销即时生效 |
| PostgreSQL EffectStore | `CORE-IMPLEMENTED` | asyncpg、编号 migration、schema v3、migration lock、事件 hash chain；旧 MCP/SQLite 路径保留原兼容语义，不具备新 intent/lease 保证，只作单测且不作为比赛证据 |
| intent-first 写入 | `CORE-IMPLEMENTED` | `prepared` + execution lease 后才调用下游；`effect_id` 是幂等键；过期 lease 才允许 reconciler 接管 |
| 恢复材料加密 | `CORE-IMPLEMENTED` | 每 Effect 随机 DEK、AES-GCM、版本化 KEK wrap、旧 key 解密与 rewrap API；Compose 使用 Docker Secret keyring |
| Undo/审批/Worker | `CORE-IMPLEMENTED` | SOD、Undo 窗口、内部签名授权、SKIP LOCKED、60s lease/20s heartbeat、5/30/120 retry、admin 有界重签；至少一次 + 下游幂等 |
| Reference ticket API | `CORE-IMPLEMENTED` | stateful PostgreSQL create/query/by-effect/cancel，`open -> cancelled`，相同补偿幂等，不同上下文 409；只在内部网络 |
| Control API | `CORE-IMPLEMENTED` | `/me`、agents、tickets、effects/timeline、Undo、assignments、livez/readyz/metrics；错误统一脱敏并带一致 trace |
| React Console/BFF | `BUILT / VISUAL-QA-PENDING` | 六固定页面、PKCE S256、内存 token、Agent confidential BFF token exchange、无角色切换；npm build/test/audit 已过，交互浏览器人工验收未做 |
| Reference Compose | `PROTOCOL-E2E-PASS / NOT READY` | PostgreSQL 17.6、Keycloak 26.7.0 和 Python/Node 基础镜像锁 digest；随机 gitignored secrets；从空 volume 重建与协议闭环已过 |
| Helm/HA | `CHART-IMPLEMENTED / KIND-PENDING` | API/Worker/Business/Console、migration、Ingress、Secret 引用、NetworkPolicy、PDB、API HPA；lint/template 通过；未做 kind、Pod 接管、rollback/外部服务替换 |

## 本轮可复核结果

- 从空 reference volumes 执行 `python scripts/reference_stack.py up` 成功；六个常驻服务健康，migration/seed 一次性任务成功。
- `/readyz`：PostgreSQL 与 OIDC/JWKS 均为 true；schema version 3；三条 seed assignment 的 tools/domains 均为 JSONB array。
- `python scripts/verify_reference_e2e.py`：真实 PKCE + token exchange；Alice immutable `sub`/assignment 验证；Effect 创建；Undo 幂等 replay；Alice self-approval 403；Dora 独立 approval；Worker compensation；结果 `compensated:cancelled:true`。
- `/metrics` 已输出 JWKS、身份拒绝原因、Effect、Undo、重试、队列深度和 active assignment。
- Console：5 tests passed，production build passed，npm audit 为 0 vulnerabilities。
- Helm 3.17.3：`helm lint --strict` 通过；默认模板 17 resources，默认 NetworkPolicy 无 `0.0.0.0/0`；未执行 kind。
- 最终 CI 口径 Ruff 通过；全仓 pytest **691 collected / 691 passed / 0 failed / 0 skipped**；`git diff --check` 通过。pytest `testpaths=["tests"]`，不包含 OAR/Auto-RedTeam 目录。

部分 reference 验证记录见 [docs/evidence/agent-identity-undo-reference-2026-07-12/README.md](docs/evidence/agent-identity-undo-reference-2026-07-12/README.md)。该目录明确未封存为最终 B6/B7 证据。

## REFERENCE-READY 差距

以下项未完成，全部通过并生成最终 manifest 后才可标记 `REFERENCE-READY`：

1. 交互式浏览器完成 Alice、Dora、Admin 三账号 UI 登录、页面隔离和录屏；当前环境没有可用浏览器控制实例，只有真实 PKCE 协议自动验收。
2. Compose 级身份负测全集：坏签名、错误 audience、伪造 human/Agent/tenant、无 assignment、撤销 assignment、跨租户不可见，并证明下游调用数为 0。
3. PostgreSQL 断连零下游；API 在下游成功/Effect 未完成窗口被杀后的 reconciler 恢复。
4. Worker 补偿中被杀、lease 到期由另一 Worker 接管，并确认工单只有一次有效取消。
5. 错误 KEK、增加新 KEK、旧记录读取与在线 rewrap 的整栈演练。
6. 双审批并发单任务、10 并发 identity/effect 新增开销 p95 ≤ 50ms、批准到恢复 ≤ 30s 的正式数据。
7. 脱敏 evidence 包：业务前后态、claims 摘要、assignment 版本、Effect/Undo events、双 trace、Gate6/Effect chain 校验和 artifact manifest。

## HA-READY 差距

- kind/Kubernetes 实际安装；API 与 Worker 至少各 2 副本。
- 删除 API Pod 不影响请求；删除 lease Worker 后另一副本接管。
- migration 重跑、滚动升级、Helm rollback 与 schema/effect 可读性。
- 外部 OIDC、PostgreSQL、key provider 各一项替换测试。
- NetworkPolicy 实际连通性证明，而不只是模板静态检查。

## Delivery v2 与赛题距离

| 层级 | 项 | 状态 |
|---|---|---|
| Tier A | D1 ≤30 页 PDF | `TODO`；草稿已增加 Identity + Undo 主创新章节 |
| Tier A | D2 代码/部署 | `PARTIAL`；主体具备，release freeze/final hash 未做 |
| Tier A | D3 ≤10 分钟视频 | `TODO`；已改为固定八镜头双人闭环脚本 |
| Tier A | D4 报名 | `TODO`；人工事项 |
| Tier B | B1–B5 六关/OAR | `DONE` |
| Tier B | B6 可信 Agent Identity | `PARTIAL`；待 REFERENCE-READY evidence 封存 |
| Tier B | B7 可验证 Undo | `PARTIAL`；待 REFERENCE-READY evidence 封存 |

比赛主叙事统一为：

> 传统 IAM 只回答谁登录，传统审计只回答发生了什么。XA-Guard 同时绑定“谁委托了哪个 Agent”，并为 Agent 的真实副作用提供受控补偿能力——前有身份、途中六关、后有撤销、全程有证据。

## 仓库与工作树

- 现有 PR #3 已合并到 `main`；本轮实现位于 `feat/identity-undo-reference`，尚未提交/推送。
- 以下既有脏改动不属于本轮 Identity + Undo，实现中未覆盖或混入：`docs/acceptance/remote-evidence/provenance-manifest.jsonl`、`open-agent-range/auto-redteam/conductor/conductor.py`、`open-agent-range/auto-redteam/tests/test_conductor_offline.py`。
- `.runtime/reference/` 被 gitignore，包含本机随机凭据与密钥，不得提交。
