# CURSOR-API-INTEGRATION · Cloud Agents REST API 集成（legacy opt-in）

> 2026-07-10 更新：默认 auto-redteam 后端已改为本地 Cursor Agent CLI / OpenCode / Codex 严格串行 proposal-only。本文仅记录 `engine: cloud` 显式开启时的旧 Cursor Cloud API 路径，不再是推荐默认路径。

> 官方文档：<https://cursor.com/docs/cloud-agent/api/endpoints> · <https://cursor.com/docs/cli/headless>
> 本文档记录 `conductor/cursor_client.py` 实际使用的端点与约定。以官方文档为准，若字段有出入以运行时 `GET /v1/models`、真实响应为准。

## 前置条件

- **付费 plan 的 User API Key**：Free plan 的 API Key **不能**用 Cloud/Background Agent API（只能用 headless CLI）。执行前用 `GET /v1/me` 确认 key 有效。
- 仓库须在 GitHub（本仓库 `origin = https://github.com/chuali-zi/agent_safety.git` ✅）。
- 环境变量 `CURSOR_API_KEY`（勿写进配置文件/仓库）。

## 鉴权

```
Authorization: Bearer $CURSOR_API_KEY
Content-Type: application/json
```
Base URL：`https://api.cursor.com`。（Basic auth 也支持，但本工作流统一用 Bearer。）

## 端点清单（本工作流用到的）

### 1. 建 agent（含初始 run）— `POST /v1/agents`
请求体：
```jsonc
{
  "prompt":   { "text": "<mission-seed.md 渲染后的种子提示>" },
  "model":    { "id": "<GET /v1/models 里的某个 id>" },
  "repos":    [ { "url": "https://github.com/chuali-zi/agent_safety", "startingRef": "auto-redteam/findings" } ],
  "envVars":  [ /* ≤50 项；名≤255B 且不得以 CURSOR_ 开头；值≤4096B；静态加密，随 agent 删除 */ ],
  "mcpServers": [ /* 可选：把 kernel/mcp_echo_server.py 作为 stdio MCP 挂给 agent 支持 live SUT */ ],
  "autoCreatePR": false,          // 首轮先攻；攻破后由 promote 阶段开启/建 PR
  "name": "oar-redteam-<objective-id>",
  "mode": "<可选 会话模式>"
}
```
返回：`agent`（含 `id`、`latestRunId`）+ 初始 `run`（`status: CREATING`）。

### 2. 追加 run（自适应 REFINE）— `POST /v1/agents/{id}/runs`
```jsonc
{ "prompt": { "text": "<followup-refine.md 渲染：依 block_reason 的变形指令>" } }
```
返回：新 `run`（`status: CREATING`）。用于闭环迭代（依据 [2025-AdaptiveAttacks](../../../docs/references/literature/06_agent_redteam/2025-AdaptiveAttacks.md)）。

### 3. 流式监控 — `GET /v1/agents/{id}/runs/{runId}/stream`
- Header：`Accept: text/event-stream`；断线用 `Last-Event-ID` 续传。
- 事件类型：`status` / `assistant` / `thinking` / `tool_call` / `interaction_update` / `heartbeat` / `result` / `error` / `done`。
- `conductor` 把每个事件按行 append 进 `console.log`（对应证据规范的 transcript）。

### 4. 取 run 结果 — `GET /v1/agents/{id}/runs/{runId}`
返回：`status` / `durationMs` / `result`(文本) / `git.branches[]`(含 PR URL)。用于 SSE 断流后的兜底轮询。

### 5. 取证据 — artifacts
- 列举：`GET /v1/agents/{id}/artifacts` → `items[]{ path, sizeBytes, updatedAt }`。
- 下载：`GET /v1/agents/{id}/artifacts/download?path=<relpath>` → 15 分钟预签名 S3 URL。
- `evidence_sync` 据此把云端 `.runtime/<run>/` 七件套拉回本地。

### 6. 用量/预算 — `GET /v1/agents/{id}/usage`
可带 `?runId=`。返回 `totalUsage` 与 `runs[]`：`inputTokens/outputTokens/cacheWriteTokens/cacheReadTokens/totalTokens`。`conductor` 据此累计估算 USD 并对照 `budget_usd` 硬上限。

### 7. 生命周期 / kill switch
- 取消 run：`POST /v1/agents/{id}/runs/{runId}/cancel` → 转 `CANCELLED`。
- 归档：`POST /v1/agents/{id}/archive` / `unarchive`（幂等）。
- 删除：`DELETE /v1/agents/{id}`（不可逆）。
- `conductor --stop`：对所有活跃 run 调 cancel，再 archive 对应 agent。

### 8. 元数据
- `GET /v1/me`：验 key（用户级返回 key 名/创建时间；服务账号返回空）。
- `GET /v1/models`：列可用模型 id（配置 `model.id` 前先查）。
- `GET /v1/repositories`：**严格限流 1/用户/分钟、30/用户/小时**——客户端必须退避，非必要不调。

## run 状态机（Cursor 侧）

`CREATING → RUNNING → (COMPLETED | FAILED | CANCELLED)`。`conductor` 以 SSE `done`/`result` 或轮询 `status` 判完成。

## 客户端实现要点（cursor_client.py）

- **仅标准库**：用 `urllib.request` 发请求、`json` 解析，便于离线测试用 `http.server` 打桩（不引第三方 HTTP 依赖）。
- **重试/退避**：对 429/5xx 指数退避；`/v1/repositories` 单独节流。
- **SSE 解析**：逐行读 `data:`，累计 `id:` 作为 `Last-Event-ID`，断线重连带上。
- **超时**：单 run 全局超时（config `run_timeout_s`），超时 → cancel_run → 记 HALT。
- **密钥卫生**：key 只从环境读，日志/证据里脱敏。

## 回退位（`--engine cli`，可选）

默认 local 路径使用本地 `agent -p --mode ask --sandbox enabled --output-format stream-json`，不使用 `--force` / `--yolo`，也不让 Cursor 直接写仓库或跑 A/B。它只返回 proposal JSON；Conductor 本地执行 OAR。
