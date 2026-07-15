# 仓库状态：XA-Guard / XA-202620

> 快照日期：**2026-07-15**（America/Los_Angeles）
> 当前统一口径：**CORE-IMPLEMENTED / DEPLOYMENT-PENDING**
> 比赛交付口径：[docs/acceptance/DELIVERY-v2.md](docs/acceptance/DELIVERY-v2.md)
> 本文件只描述当前状态；工作历史见 [log.md](log.md)。

## 总体结论

XA-Guard 六关、OAR 主评测和新 Identity + Undo 核心代码均已实现。Reference Compose 已从空 PostgreSQL volume 一键构建启动，并通过真实 Keycloak Authorization Code + PKCE、Standard Token Exchange V2、Alice 创建工单、Alice 自批拒绝、Dora 独立批准、Worker 补偿、业务 `open -> cancelled` 的协议级闭环。

当前仍**不是** `REFERENCE-READY`，也不是 `HA-READY`：Reference core 身份负测和核心故障场景已在全新 volume 上 7/7 通过，但 Worker 长时接管/retry、KEK、并发性能、三账号 UI、最终 evidence manifest 和 kind 多副本尚未封存。Delivery v2 的 B6/B7 因此保持 `PARTIAL`，不得改写为生产 IAM、绝对 exactly-once 或通用数据库 Undo 已落地。

## 当前能力状态

| 能力面 | 状态 | 当前事实与边界 |
|---|---|---|
| Gate1–6 与 Gate6 审计 | `DONE` | 既有 MCP/demo/OAR 路径保留；新原动作和补偿也进入相同 Pipeline |
| OAR B1–B5 主证据 | `DONE` | canonical Null vs XA-Guard A/B、ledger replay 与 audit 对齐保持原状态 |
| Keycloak/OIDC 身份 | `CORE-IMPLEMENTED` | discovery/JWKS 启动必需；普通离线验签；敏感接口 introspection；`act.sub` 优先、Keycloak `azp` reference 映射；未知 kid 有刷新、负缓存和节流 |
| 动态 Agent assignment | `CORE-IMPLEMENTED` | PostgreSQL human/group→Agent→tool/data-domain，有效期/版本/变更人；每次调用与 YAML ceiling 相交，撤销即时生效 |
| PostgreSQL EffectStore | `CORE-IMPLEMENTED` | asyncpg、编号 migration、schema v4、migration lock、事件 hash chain；旧 MCP/SQLite 路径保留原兼容语义，不具备新 intent/lease 保证，只作单测且不作为比赛证据 |
| intent-first 写入 | `CORE-IMPLEMENTED` | `prepared` + execution lease 后才调用下游；`effect_id` 是幂等键；过期 lease 才允许 reconciler 接管 |
| 恢复材料加密 | `CORE-IMPLEMENTED` | 每 Effect 随机 DEK、AES-GCM、版本化 KEK wrap、旧 key 解密与 rewrap API；Compose 使用 Docker Secret keyring |
| Undo/审批/Worker | `CORE-IMPLEMENTED` | SOD、Undo 窗口、内部签名授权、SKIP LOCKED、60s lease/20s heartbeat、5/30/120 retry、admin 有界重签；至少一次 + 下游幂等 |
| Reference ticket API | `CORE-IMPLEMENTED` | stateful PostgreSQL create/query/by-effect/cancel，`open -> cancelled`，相同补偿幂等，不同上下文 409；只在内部网络 |
| Control API | `CORE-IMPLEMENTED` | `/me`、agents、tickets、effects/timeline、Undo、assignments、livez/readyz/metrics；错误统一脱敏并带一致 trace |
| React Console/BFF | `BUILT / VISUAL-QA-PENDING` | 六固定页面、PKCE S256、内存 token、Agent confidential BFF token exchange、无角色切换；已修正 human assignment 与 If-Match 契约，npm build/test/audit 已过，交互浏览器人工验收未做 |
| Reference Compose | `CORE-FAULT-PASS / NOT READY` | PostgreSQL 17.6、Keycloak 26.7.0 和 Python/Node 基础镜像锁 digest；随机 gitignored secrets；从空 volume 重建、协议闭环和 core fault 7/7 已过 |
| Helm/HA | `CHART-IMPLEMENTED / KIND-PENDING` | API/Worker/Business/Console、migration、Ingress、Secret 引用、NetworkPolicy、PDB、API HPA；lint/template 通过；未做 kind、Pod 接管、rollback/外部服务替换 |

## 本轮可复核结果

- 从空 reference volumes 执行 `python scripts/reference_stack.py up` 成功；六个常驻服务健康，migration/seed 一次性任务成功。
- `/readyz`：PostgreSQL、key provider 与 OIDC/JWKS 均为 true；schema version 4；reference assignment 的 tools/domains 均为 JSONB array。
- `python scripts/verify_reference_e2e.py`：真实 PKCE + token exchange；Alice immutable `sub`/assignment 验证；Effect 创建；Undo 幂等 replay；Alice self-approval 403；Dora 独立 approval；Worker compensation；结果 `compensated:cancelled:true`。
- `verify_reference_faults.py --suite core`：全新 volume 首轮发现 PostgreSQL 恢复后未等待 Keycloak；修复编排后 7/7 通过，包括身份伪造零下游、assignment 即时撤销、跨租户隔离、PostgreSQL 断连零下游、prepared reconciler 和双审批单任务。
- `/metrics` 已输出 JWKS、身份拒绝原因、Effect、Undo、重试、队列深度和 active assignment。
- Console：5 tests passed，production build passed，npm audit 为 0 vulnerabilities。
- Helm 3.17.3：`helm lint --strict` 和 deployment tests 10/10 通过；仓内 kind/kubectl/helm 可执行，但未执行真实 kind 集群、Pod 接管或 rollback。
- 当前 release-candidate 口径：Ruff 通过；全仓 pytest **772 collected / 771 passed / 0 failed / 1 skipped**，唯一 skip 为 Windows 目录 symlink 不可用；OAR kernel + Auto-RedTeam **149 passed**；L3 static 11/11；`git diff --check` 通过。代码已提交推送，但 D2 final artifact hash 尚未生成。
- 远端 GitHub Quality run `29418343744`：Python 3.10 与 3.12 矩阵均通过；此前 3.10 暴露的 Kind `datetime.UTC` 和 gmssl 偶发不可自验签名已由 `f157f92` 修复。

部分 reference 验证记录见 [docs/evidence/agent-identity-undo-reference-2026-07-12/README.md](docs/evidence/agent-identity-undo-reference-2026-07-12/README.md)。该目录明确未封存为最终 B6/B7 证据。

## REFERENCE-READY 差距

Core 身份负测、assignment 撤销/跨租户隔离、PostgreSQL 零下游、prepared reconciler 与双审批单任务已通过，但尚未封存。以下项仍未完成，全部通过并生成最终 manifest 后才可标记 `REFERENCE-READY`：

1. 交互式浏览器完成 Alice、Dora、Admin 三账号 UI 登录、页面隔离和录屏；当前环境没有可用浏览器控制实例，只有真实 PKCE 协议自动验收。
2. Worker 补偿中被杀、lease 到期由另一 Worker 接管，并确认 5/30/120 retry 和工单只有一次有效取消。
3. 错误 KEK、增加新 KEK、旧记录读取与在线 rewrap 的整栈演练。
4. 10 并发 identity/effect 新增开销 p95 ≤ 50ms、批准到恢复 ≤ 30s 的正式数据。
5. 脱敏 evidence 包：业务前后态、claims 摘要、assignment 版本、Effect/Undo events、双 trace、Gate6/Effect chain 校验和 artifact manifest。

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

- `feat/identity-undo-reference` 已经 fast-forward 合并并推送远端 `main`；功能提交为 `07f7342` 与 `94041f6`，未改写历史。
- `94041f6` 同时包含 Auto-RedTeam provider safety quarantine 与追加 provenance；后续回归审查应继续把它们作为独立关注面核对。
- `.runtime/reference/`、`.runtime/kind-ha/` 与 `.runtime/evidence/` 被 gitignore，包含本机随机凭据、密钥或未封存验收输出，不得提交。
