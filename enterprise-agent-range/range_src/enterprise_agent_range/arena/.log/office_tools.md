# office_tools.py 工作日志

2026-07-02：新增 Task 5，实现背靠 `World` 的 office 工具集。

- `read_mail`/`query_project`/`send_email` 均为 `(world, principal, args) -> dict` 纯函数式 handler，直接调用 `World.inbox`/`world.projects.get`/`World.record_egress`，不重复实现邮件/项目/泄露检测逻辑。
- `query_project` 对未知 `project_id` 返回 `{"found": False, "project_id": ...}`，不抛异常。
- `send_email` 把 `record_egress` 的结果（`external`/`sensitive_hits`）透传给调用方，泄露判定逻辑仍在 `world.py`/`sensitive.py`，工具层不重复实现。
- `OFFICE_TOOLS` 注册表按工具名映射三个 handler，供上层 orchestrator 按名调用。

严格按 TDD：先写 `tests/test_arena_office_tools.py`（4 用例）确认 `ModuleNotFoundError` 失败，再实现 `office_tools.py`，4 用例全部通过；`test_arena_*.py` 全量 14 用例无回归。未改动 `world.py`/`sensitive.py`，未新增其它 arena 模块（YAGNI）。commit: 1313df6。
