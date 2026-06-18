# proxy 模块工作日志

---

## 2026-06-17 Codex 主 agent
- pending ledger 脱敏升级为 schema 标注优先：支持 `x-xa-guard-sensitive`、`x-sensitive`、`writeOnly`、`format=password`，并递归处理 object properties、array items 和 dict 型 additionalProperties。
- `upstream.py` 在 `_build_app()` 建立 tool inputSchema 映射，pending add/list 以及 MCP elicitation message 都使用 schema-aware redaction。
- Docker profile 静态 manifest 为 `send_email.to` / `send_email.body` 增加少量敏感 schema 标注，作为 L3 demo 证据。
- 字段名 best-effort 仍保留为 schema 缺失时的 fallback；重启后脱敏参数继续 fail-closed，不用占位值执行下游。
- 限制：不是完整 JSON Schema 解释器，也不是自由文本 DLP 或 KMS 加密恢复。

---

## 2026-06-17 Codex 主 agent
- `pending.py` 新增 pending ledger 参数脱敏：对 password/token/secret/api_key/authorization/cookie 等常见敏感键递归脱敏，并保留参数 sha256 供比对。
- `upstream.py` 的 pending list 改为返回脱敏参数，避免控制工具泄露敏感明文。
- 重启后若 pending 参数只能从 ledger 恢复为脱敏值，approve 会 fail-closed，调用 `pipeline.reject_after_approval()` 追加 `deny` 审计，不触达下游。
- 当前进程内未重启的 pending 仍可用内存原始参数完成 approve；ledger 不保存 approval token/operator token/工具结果/敏感参数原文。
- 限制：字段名驱动 best-effort，不是完整 DLP、schema 感知脱敏或 KMS 加密恢复。

---

## 2026-06-17 Codex 主 agent
- 新增 `pending.py`：`PendingApprovalStore` 支持可选本地 JSONL ledger，记录 pending add/remove 生命周期，启动时重放 ledger 恢复未过期项。
- `upstream.py` 的 pending fallback 从纯进程内 dict 切换为 store 抽象；可通过 `XA_GUARD_PENDING_APPROVAL_STORE` 或配置项 `pending_approvals_path` 指定 ledger 路径。
- ledger 保存审批恢复所需的 `GateContext` 快照，但不保存 approval token、operator token 或工具执行结果；approve 时才现场签发 one-shot token。
- 单元与 MCP E2E 已覆盖 app 重建后 pending list/approve/reject、TTL 过期清理、token 不落 ledger 与审计链 `require_approval -> allow`。
- 限制：这是单机本地恢复原型，未实现多实例一致性、文件锁、完整 RBAC 或参数脱敏策略。

---

## 2026-06-17 Codex 主 agent
- HITL reject 路径加固：elicitation reject 与 pending reject 都调用 `pipeline.reject_after_approval()`，追加 `deny` 审计行，记录人工拒绝的 approver/reason，下游仍不执行。
- approval token 加固：`pipeline.run_after_approval()` 使用 `verify_and_consume_approval()`，同一 token 在当前进程内只能驱动一次执行，重放会拒绝。
- operator token 覆盖面扩展：配置 `XA_GUARD_APPROVAL_OPERATOR_TOKEN` 后，`xa_guard_list_pending_approvals`、approve、reject 都要求传入匹配 token。

---

## 2026-06-17 Codex 主 agent
- `upstream.py` 新增无 elicitation 客户端的 HITL pending approval fallback：红色工具触发 `REQUIRE_APPROVAL` 后保存原始 `GateContext`，返回 `trace_id` 等待人工控制工具处理。
- 新增内置 MCP 控制工具 `xa_guard_list_pending_approvals` / `xa_guard_approve_pending`，在 upstream 本地短路，不进入下游和普通 pipeline。
- pending approve 会签发现有 approval token 并调用 `pipeline.run_after_approval()`；approve/reject 后删除 pending 项，重复 approve 不会再次执行下游；配置 `XA_GUARD_APPROVAL_OPERATOR_TOKEN` 时会强制校验 `operator_token`。
- 单元与 MCP E2E 已覆盖 pending、list、approve、reject、一次性消费和 `require_approval -> allow` 审计闭环。

---

## 2026-06-17 Codex 主 agent
- `DownstreamRouter` 支持 `DownstreamSpec.tools` 静态工具 manifest；有 manifest 时 `start()` 只注册工具元数据，不启动原生 stdio downstream 做 `list_tools`。
- 静态 discovery 下若调用阶段仍是 native，会 fail-closed；docker profile 通过 Gate5 `sandbox_all_tools=true` 让调用进入 sandbox。
- 新增 L3 compose smoke，断言 docker profile 下 router `_sessions == {}` 且工具列表可暴露。

---

## 2026-05-25 agent-P
- 实现 downstream.py：mcp>=1.27 client，AsyncExitStack 管理 stdio_client + ClientSession 生命周期；start() 拉取并缓存 tools，list_tools/call_tool/stop 完整。
- 实现 upstream.py：Server("xa-guard") + stdio_server；@list_tools 透传下游元数据，@call_tool 构造 GateContext 跑 pipeline，DENY 时返回 TextContent 提示，放行时透传下游 CallToolResult.content。
- run_streamable_http 留 NotImplementedError（mcp 1.27 仅暴露 StreamableHTTPServerTransport 低层，需 ASGI 集成）；elicitation HITL TODO。
- 新增 tests/integration/{_fixture_echo_server.py,test_proxy_smoke.py}：用本地最小 stdio MCP 替代未完工的 ops_target，覆盖 start/list_tools/benign call/malicious DENY/stop。全套 71 测试全绿。

## 2026-05-24 23:55 主助手
- upstream.py / downstream.py 接口骨架
- 决策：upstream 双协议（stdio + Streamable HTTP），demo 阶段 stdio 优先
- 决策：DownstreamRouter 单例，name → session 映射；start() 阶段拉取所有下游 tools 缓存
- TODO（agent-P）：mcp.client.session 集成；ToolMeta 标准化；elicitation 反向问需配合关卡 2
