# XA-Guard Console + BFF

React/TypeScript/Vite 控制台与同源 Node/Express BFF。页面覆盖：

- 我的 Agent：human → Agent → tool → data domain 身份链；
- 发起工单：指定当前已授权 Agent 执行业务写操作；
- 操作影响：Effect、Undo 窗口、恢复状态与事件；
- 待我审批：独立审批账号批准或拒绝，不提供角色切换；
- 身份与 Agent：管理员在静态 ceiling 内管理动态 assignment；
- 审计证据：原动作 trace、补偿 trace、业务引用和 Effect hash chain。

## 身份与 token 边界

浏览器使用 `keycloak-js` 的 Authorization Code + PKCE S256。Keycloak 实例及
access/refresh token 只保存在 JavaScript 内存中；应用不调用 `localStorage`、
`sessionStorage`、IndexedDB 或持久 cookie。刷新或关闭页面即丢失应用内 token。

每个 `/control/v1` 请求携带 human bearer 与 `X-Agent-ID` 到同源 BFF。BFF 用
confidential client 执行 RFC 8693 标准 token exchange，并以交换后的 Agent token
调用 Control API。Agent token 只存在于单次 Node 请求的局部变量中，不写日志、
cookie、session、cache 或响应，因此浏览器永远看不到它。

BFF 必需环境变量：

| 变量 | 说明 |
|---|---|
| `OIDC_ISSUER` | Keycloak realm issuer；生产必须 HTTPS |
| `OIDC_CONFIDENTIAL_CLIENT_ID` | BFF confidential client |
| `OIDC_CLIENT_SECRET` 或 `_FILE` | client secret；`_FILE` 优先 |
| `CONTROL_API_BASE_URL` | 内部 XA-Guard Control API 地址 |
| `PORT` | BFF/静态站点端口，默认 `8080` |

为兼容 reference Compose，BFF 同时接受 `KEYCLOAK_URL`、`KEYCLOAK_PUBLIC_URL`、`KEYCLOAK_REALM`、
`KEYCLOAK_CLIENT_ID`、`KEYCLOAK_CLIENT_SECRET(_FILE)` 和 `CONTROL_API_URL`。
生产默认要求 HTTPS issuer；仅 loopback、Compose 中精确名为 `keycloak` 的内部
服务，或显式设置
`XA_GUARD_DEPLOYMENT_PROFILE=reference` 的内部 `keycloak`/cluster Service，允许
HTTP。该例外不能用于远程生产 IdP。
`KEYCLOAK_PUBLIC_URL` 只用于浏览器 CSP，token exchange 仍走内部
`KEYCLOAK_URL`，不会把容器内服务名泄漏到前端配置。

公开浏览器配置位于 `/config/config.json`，只包含 issuer、public client ID、API
路径和默认 Agent ID，不得放入 client secret。

## 本地开发与验证

```bash
cd console
npm ci
npm test
npm run build

# 两进程开发模式：Vite :5173，BFF :8080
OIDC_ISSUER=https://id.example.gov/realms/xa-guard \
OIDC_CONFIDENTIAL_CLIENT_ID=xa-guard-bff \
OIDC_CLIENT_SECRET_FILE=/run/secrets/oidc-client-secret \
CONTROL_API_BASE_URL=http://127.0.0.1:3000 \
npm run dev
```

Windows PowerShell 请分别设置同名 `$env:` 变量。开发环境的
`public/config/config.json` 需指向同一 Keycloak realm/public client。

## 容器

```bash
docker build -t xa-guard-console:0.1.0 console
docker run --rm -p 127.0.0.1:8080:8080 \
  -e NODE_ENV=production \
  -e OIDC_ISSUER=https://id.example.gov/realms/xa-guard \
  -e OIDC_CONFIDENTIAL_CLIENT_ID=xa-guard-bff \
  -e OIDC_CLIENT_SECRET_FILE=/run/secrets/oidc-client-secret \
  -e CONTROL_API_BASE_URL=http://xa-guard-api:8080 \
  xa-guard-console:0.1.0
```

生产容器由 Node 同时提供静态资源与 BFF，避免跨站 token 传输。Dockerfile 使用
非 root 用户、固定 Node patch tag，并通过 `/healthz` 健康检查。发布时仍应将基础
镜像与应用镜像进一步锁定到审核通过的 digest。

直接依赖许可证与构建期 CC-BY-4.0 数据归属见
[`THIRD_PARTY_NOTICES.md`](./THIRD_PARTY_NOTICES.md)。
