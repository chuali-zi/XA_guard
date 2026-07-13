# 2026-07-12 Auto-RedTeam 真实运行维护

- 修复业务失败误报进度、失败目标误标 covered、连续错误不熔断、重启丢变体状态和陈旧 campaign lock；模型分工为外层 GPT Sol、靶场 OpenCode DeepSeek。
- 修复 CLI 参数、Windows Codex launcher、schema 和 JSONL 解析；补齐 rag-index 等目标 surface allowlist。mailbox/rag/ticket/rag-index 完整 run 均封存为 LIMIT，维护器健康运行。27 项测试与 Ruff 通过。

# 2026-07-12 Auto-RedTeam 持续运行维护

- 新增跨平台前台 supervisor `maintain.py`：监控进程与状态进度，异常退出指数退避恢复，重启频率熔断，正常完成不误重启。
- 增加原子状态、持久 stop/resume、单实例锁、陈旧锁回收、日志轮转和离线单测；未合并 `feat/cursor-auto-redteam` 的 Conductor 源码，当前 main 需先整合该实现才能真实运行。
