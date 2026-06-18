# sdk 模块工作日志

---

## 2026-06-17 Codex
- 从 `xa_guard.sdk.decorators` 抽出 `preflight_tool_call()`，供 decorator 和第三方集成共用同一套非透传 preflight 语义。
- 新增 `xa_guard.integrations.langchain.protect_tool()`，用于包装单个 LangChain `BaseTool` 的 `_run/_arun`；阻断时抛 `XAGuardBlocked`，不调用原工具。
- 当前环境未安装 `langchain_core`，`tests/test_langchain_integration.py` 按可选依赖 skip；SDK decorator 测试仍通过。
- 边界：未承诺完整 LangChain Agent / CallbackHandler / LangGraph / HITL resume。

---

## 2026-06-16 21:50 Codex
- 将历史顶层 `sdk` 入口改为兼容转发，真实 SDK 实现放入可打包命名空间 `xa_guard.sdk`。
- 新增 `@protect` 非透传 preflight：调用原函数前先跑 XA-Guard pipeline；DENY/REQUIRE_APPROVAL 抛 `XAGuardBlocked`，不调用原函数。
- 已补 `tests/test_sdk_protect.py` 覆盖 public imports、sync allow、dangerous block、async allow；完整 LangChain Callback/Tool wrapper 仍未实现。

## 2026-05-24 23:55 主助手
- decorators.py 占位 @protect
- M2+ 由 agent-SDK 实现 LangChain CallbackHandler 适配
