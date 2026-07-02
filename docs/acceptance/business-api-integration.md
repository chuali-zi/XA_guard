# 实际下游业务 API 接入验收说明

本接入把真实业务 HTTP API 包装成固定 MCP tools，并继续经过 XA-Guard 的治理预检、Gate1-6、HITL、污点和审计链。它不是系统级安装，不写 Windows 用户/系统环境变量，不写 Trae/Cursor/OpenCode 用户目录配置，也不在仓库外创建 key、日志或证据文件。

## 本地配置

在仓库根目录按 `.env.example` 新建本机 `.env`：

```dotenv
BUSINESS_API_BASE_URL=https://business-api.example.com
BUSINESS_API_KEY=replace-with-local-api-key
BUSINESS_API_TIMEOUT_SECONDS=10
BUSINESS_API_ALLOW_INSECURE_LOCAL=false
```

加载顺序为：进程环境变量优先，其次读取仓库根目录 `.env`。`.env` 和 `.env.*` 必须被 `.gitignore` 忽略；真实 API key 不提交、不打印、不进入审计。

`BUSINESS_API_BASE_URL` 默认只允许 `https://`。本地 mock 测试可以显式设置 `BUSINESS_API_ALLOW_INSECURE_LOCAL=true` 并使用 `http://127.0.0.1:<port>`。

## 暴露的 MCP Tools

- `business_get_status`：GET `/status`，查询业务 API 状态，风险 green。
- `business_query_record`：GET `/records/{record_id}`，查询业务记录，风险 yellow，外部网络能力标为 `NETWORK_EXTERNAL`。
- `business_submit_ticket`：POST `/tickets`，提交业务工单，风险 red，触发 Gate2/Gate3 人工审批。

不会暴露任意 URL、任意 method 或任意 header 注入能力。Authorization 只在 adapter 内部生成，永不回传给上游。

## 启动

```powershell
$env:PYTHONPATH='src;.'
python -m xa_guard.server --config configs/xa-guard.business-api.yaml
```

调用方启用企业治理时应在 `_xa_guard` envelope 中提供：

```json
{
  "tenant_id": "acme-corp",
  "principal_id": "bob.dev@acme.local",
  "agent_id": "general-office-agent",
  "data_domain": "engineering_docs",
  "resource_owner": "bob.dev@acme.local",
  "task_id": "business-api-smoke",
  "cost_estimate_usd": 0.05
}
```

XA-Guard 会剥离 `_xa_guard`，下游业务 API 只看到业务参数。

## 失败处理与脱敏

- `.env` 缺失或缺少 `BUSINESS_API_BASE_URL` / `BUSINESS_API_KEY` 时 fail-closed，返回 `configuration_error`。
- 401/403 返回 `auth_error`，429 返回 `rate_limited`，5xx 返回 `upstream_error`。
- HTTP 错误只返回状态码、错误类别、`request_id` / `correlation_id` 和通用消息，不记录响应体。
- 成功响应会递归脱敏 `authorization`、`cookie`、`token`、`secret`、`password`、`api_key` 等字段。
- pending ledger 和 Gate6 audit 不包含 API key；Gate6 仍记录工具名、业务参数、结果 hash、policy hits 和 governance 字段。

## 验收命令

```powershell
$env:PYTHONPATH='src;.'; python -m pytest tests/unit/test_business_api_adapter.py -q
$env:PYTHONPATH='src;.'; python -m pytest tests/integration/test_business_api_downstream.py -q
$env:PYTHONPATH='src;.'; python -m pytest tests/integration/test_full_gate_stress_extra.py tests/test_pipeline_smoke.py tests/unit/test_gate4.py -q
$env:PYTHONPATH='src;.'; python -m ruff check demo/targets/business_api_target.py tests/unit/test_business_api_adapter.py tests/integration/test_business_api_downstream.py
```

## 明确边界

本轮只接下游业务 HTTP API，不接 Gate1 模型 API 或 OpenAI-compatible LLM API。不接真实 SSO、SCIM、LDAP、JWT 验签、真实审批后台或真实账单系统。后续如需写 Trae/Cursor/OpenCode 用户配置、Windows 系统环境变量、系统 PATH 或仓库外文件，必须先单独确认目标路径和风险。
