# sut.py 工作日志

2026-07-02：新增 Task 6，实现 SUT（System-Under-Test）决策替身。

- `SUT` 基类：`decide(principal, call) -> (decision, reason)` 由子类实现；`invoke` 统一记录 `AuditRecord` 到 `self.audit`，deny 时直接返回 `{"decision": "deny", "reason", "executed": False}` 且不调用 `OFFICE_TOOLS`（不产生 egress），allow 时才调用 `OFFICE_TOOLS[call.tool]` 并补充 `decision`/`executed` 字段。
- `NullSUT`：透传替身，任何调用都 allow，直接复用 `SUT.invoke` 执行工具。
- `GuardStubSUT`：确定性策略替身，仅在 `send_email` 且 `is_external_destination(to)` 且 `find_sensitive_hits(body)` 同时成立时 deny；其余情况（读操作、内部发送、非敏感外发）一律 allow。判定逻辑复用 `enterprise_agent_range.sensitive`，不重复实现。

严格按 TDD：先写 `tests/test_arena_sut.py`（4 用例）确认 `ModuleNotFoundError: arena.sut` 失败，再实现 `sut.py`，4 用例全部通过；全量 `tests/` 221 用例无回归。仅新增 `sut.py` + 测试文件，未改动 `world.py`/`office_tools.py`/`sensitive.py`（YAGNI）。commit: efe3724。
