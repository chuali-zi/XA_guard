# integrations 模块工作日志

---

## 2026-06-17 Codex
- 新增 LangChain 可选集成模块 `langchain.py`。
- 提供 `protect_tool()`：包装单个 `langchain_core.tools.BaseTool`，在 `_run/_arun` 前调用 XA-Guard `preflight_tool_call()`。
- 决策：先做强阻断 Tool wrapper，不做容易被 callback manager 吞异常的 CallbackHandler；完整 Agent/LangGraph 集成后续再补。
