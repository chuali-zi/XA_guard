# Agent Identity + Undo 参考架构

> 当前口径：`CORE-IMPLEMENTED / REFERENCE-VALIDATION-IN-PROGRESS`。本文描述已经进入正式代码路径的实现，以及尚未完成的部署验收；不把代码存在等同于生产落地。

## 1. 主链路

```text
Keycloak human login (Authorization Code + PKCE)
  -> Console/BFF standard token exchange
  -> human sub + Agent azp/act.sub + tenant + roles/groups
  -> PostgreSQL dynamic assignment ∩ YAML immutable ceiling
  -> XA-Guard Gate1–6
  -> prepared Effect intent
  -> stateful ticket API (effect_id idempotency key)
  -> encrypted recovery + available Effect
  -> independent Undo request/approval
  -> signed internal compensation authorization
  -> lease-based Worker -> Governance + Gate1–6 -> idempotent cancel
  -> Effect events + Gate6 audit evidence
```

传统 IAM 回答“谁登录”，传统审计回答“发生了什么”。这条链路同时绑定“谁委托了哪个 Agent”，并为 Agent 已经产生的真实副作用提供受控补偿：前有身份、途中六关、后有撤销、全程有证据。

## 2. 双主体身份与撤销即时生效

Reference 环境使用 Keycloak 26.7.0。浏览器只执行 Authorization Code + PKCE S256，token 由 `keycloak-js` 保存在内存；BFF 以 confidential Agent client 执行 Standard Token Exchange V2，交换后的 Agent token 只存在于单次代理请求的局部变量中，不回传浏览器、不写 cookie/存储/日志。

控制 API 启动时必须完成 OIDC discovery 与 JWKS 获取。普通调用离线验签；审批、重试和 assignment 变更额外 introspection，IdP 不可达时失败关闭。JWKS 遵守缓存头，未知 `kid` 强制刷新一次，并有并发合并、负缓存和刷新节流；普通调用最多允许 15 分钟 stale grace，敏感调用没有 grace。

可信身份映射如下：

- `sub`：不可变人员 ID；`preferred_username` 仅作显示与业务标识。
- `act.sub`：外部 STS 的标准 Agent actor，存在时优先。
- `azp`：Keycloak reference 环境的 Agent client ID。
- `tenant_id`、realm/client roles、groups：租户与权限输入。

PostgreSQL assignment 支持 human 或 group 到 Agent 的工具、数据域、有效期、版本和变更人。每次调用都重新计算动态 assignment 与当前 YAML ceiling 的交集，因此撤销关系或缩小 ceiling 无需等待 token 过期。管理员只能在 ceiling 内授权，不能扩大 Agent 固有能力。

## 3. intent-first Effect 与补偿状态机

严格 reference 路径使用异步 PostgreSQL/asyncpg `EffectStore`。写工具必须有 v2 副作用合同，合同包含版本/hash、成功谓词、可逆性、Undo 窗口、恢复字段、补偿工具、参数映射、幂等键、重试和 reconciliation。没有合同的写操作在严格模式下拒绝；不可逆操作进入 `manual_required`，不展示虚假 Undo。

写入顺序固定为：

1. PostgreSQL 创建 `prepared` intent 和 60 秒 execution lease；数据库不可用时不会调用下游。
2. 使用 `effect_id` 作为下游幂等键调用业务 API。
3. 成功后用随机 DEK 加密恢复材料；版本化 KEK 包裹 DEK，再保存合同快照和结果摘要。
4. API 在下游成功后崩溃时，reconciler 只接管已过期 execution lease，并按 `effect_id` 查询业务状态。

状态机为：

```text
prepared -> available -> undo_pending -> approved -> compensating -> compensated
               |              |              |              |
             expired        rejected       retry_wait     compensation_failed
               \__________________________________________ manual_required
```

Undo 请求和审批都必须在 `undo_expires_at` 前完成；已批准任务不会因窗口随后结束而被丢弃。每个恢复材料使用 AES-GCM 随机 DEK，DEK 用活动 KEK 包裹；keyring 同时保留新写 key 和旧解密 key，并支持在线 rewrap。SQLite 后端只保留旧 MCP/本地单测兼容，不作为比赛实际落地证据；SQLite 导入 PostgreSQL 时只迁移公开 provenance，并强制 `manual_required`，不会伪造可恢复能力。

## 4. 独立 Worker 与语义边界

Worker 使用 `FOR UPDATE SKIP LOCKED`、60 秒 lease、20 秒 heartbeat。网络超时、429 和 5xx 按合同的 5/30/120 秒最多重试三次；策略拒绝、4xx、参数和签名错误不自动重试。heartbeat 丢失会取消本地补偿，所有完成/失败写入仍以 lease owner 条件更新。

审批时生成绑定 effect、request、approver、tenant、Agent、参数 hash 和过期时间的内部签名授权。Worker 不保存或重放原始 JWT，补偿前会再次检查实时 assignment 与 ceiling，并重新进入 Governance + Gate1–6。永久失败仅允许经敏感 introspection 的 `undo.admin` 重签 15 分钟执行票据。

系统语义是“至少一次调度 + 下游幂等实现有效一次”，不宣称分布式绝对 exactly-once。取消本地 HTTP task 也不能撤回已经到达下游的网络副作用，因此业务 API 的幂等合同是正确性的必要组成。

## 5. Control API 与参考工单

受 Bearer 保护的统一应用服务提供：

- `GET /control/v1/me`、`GET /control/v1/agents`
- `POST /control/v1/tickets`
- `GET /control/v1/effects`、`GET /control/v1/effects/{id}`
- `POST /control/v1/effects/{id}/undo-requests`
- `GET /control/v1/undo-requests?status=pending`
- `POST /control/v1/undo-requests/{id}/decision`
- `POST /control/v1/undo-requests/{id}/retry`
- `GET/POST/DELETE /control/v1/assignments`

错误固定为 `{code, message, trace_id}`，不返回 recovery、原始 token、数据库错误或下游 secret。参考工单 API 支持创建、查询、按 effect 查询和取消；`open -> cancelled`，相同补偿幂等返回成功，不同参数上下文返回 409。

Console 固定六页：我的 Agent、发起工单、操作影响、待我审批、身份与 Agent、审计证据。Alice 和 Dora 使用独立登录会话，Alice 页面没有角色切换或伪装审批入口。

## 6. 部署与密钥

Reference Compose 由 PostgreSQL、Keycloak、migration/seed、XA-Guard API、Worker、工单 API、Console/BFF 组成：

```powershell
python scripts/reference_stack.py up
python scripts/verify_reference_e2e.py
```

bootstrap 将随机密码、client secret、session/internal authorization key 和 KEK keyring 写入 gitignored `.runtime/reference/`，以 Docker Secret 挂载。对外端口只绑定 loopback；远程环境必须使用 TLS 和组织 Secret/KMS。

Helm chart 位于 `deploy/helm/xa-guard/`，默认引用外部 OIDC、PostgreSQL 与 key provider，`referenceInfra.enabled=false`。它提供 API/Worker/Business/Console、migration Job、ConfigMap/Secret 引用、Ingress、NetworkPolicy、PDB 和 HPA 基线；kind、多副本接管、rollback 与外部服务替换仍属于 `HA-READY` 待验收项。

## 7. 已验证与未验证

已实际验证：镜像构建、Compose 启动、migration v3、OIDC/JWKS ready、缺 token 401、真实 Alice/Dora Authorization Code + PKCE、Standard Token Exchange V2、dynamic assignment、intent/effect、Alice 自批拒绝、Dora 独立批准、Worker 补偿、工单 `cancelled`、双 trace 分离、相关单元/回归测试。

尚未完成：交互式浏览器三账号人工 UI 录屏；全部身份负测的 Compose 级自动化；PostgreSQL 断连零下游、API crash-window reconciler、Worker kill/lease takeover、KEK rewrap 的整栈故障注入；10 并发 p95；kind 两副本、NetworkPolicy 证明、rollback 与外部 OIDC/PostgreSQL/KMS 替换。完成这些项前不得标记 `REFERENCE-READY` 或 `HA-READY`。

依赖合规：Keycloak/asyncpg/项目代码为 Apache-2.0，PostgreSQL 使用 PostgreSQL License，Starlette/HTTPX 为 BSD-3-Clause，PyJWT 为 MIT，cryptography 为 Apache-2.0/BSD，Console 直接依赖许可证见 `console/THIRD_PARTY_NOTICES.md`。
