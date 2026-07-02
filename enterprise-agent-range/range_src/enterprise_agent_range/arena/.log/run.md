# run.py 工作日志

2026-07-02：新增 Task 9（最终任务），实现编排入口 + 端到端 2×2，证明整条切片的 DoD。

- `run_challenge(challenge, seat, sut, manifest_root) -> RunResult`：串联 `build_world_for` → `seat.run` → `evaluate`，产出含 `audit`/`egress`/`verdict`/`trace_hash` 的证据字典；`trace_hash` 用 `io_utils.sha256_text(stable_json_dumps(...))` 计算，未重复造轮子。
- 新增 `cases/arena/OFFICE-INJ-001.attack.json` 与 `.control.json`：两者 `world` 均为 `office-baseline`、`task.prompt` 完全一致，仅 `inject`/`kind`/`oracle` 不同——这是"环境与题库解耦"的直接证明。
- `tests/test_arena_end_to_end.py` 三用例：attack/control 共享 task+world；2×2 矩阵（GullibleAgent × {GuardStubSUT, NullSUT} × {attack, control}）验证 GuardStub 拦截攻击且无误报放行良性对照，NullSUT 放行攻击导致外泄，A/B 防护差值可见；证据字典含 audit 与 sha256 前缀的 trace_hash。

严格按 TDD：先建 challenge JSON + 测试，确认 `ModuleNotFoundError: arena.run` 失败；再实现 `run.py`，3 用例全部通过；`test_arena_*.py` 全量 27 用例无回归；全仓库 `tests/` 230 用例全绿，未破坏既有靶场测试。仅新增 `run.py` + 2 个 challenge JSON + 测试文件（YAGNI），未改动其余 arena 模块。commit: dad126d。
