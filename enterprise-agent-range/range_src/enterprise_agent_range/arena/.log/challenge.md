# challenge.py 工作日志

2026-07-02：Task 3，新增解耦的 Challenge 数据模型 `challenge.py`。

- `Injection`/`Task`/`OracleSpec`/`Challenge` 均为 frozen dataclass，仅描述「注入+中性任务+判据」三层，不含任何硬编码执行步骤。
- `challenge_from_dict(data)` 解析嵌套字典；`inject` 缺省为空列表（对照组无注入）；`OracleSpec` 提供默认值 `data_exposure_absent=True`、`downstream_external_send_count=0`。
- `load_challenge(path)` 从 JSON 文件读取后复用 `challenge_from_dict`。

严格按 TDD：先写 `tests/test_arena_challenge.py`（3 用例）确认 `ModuleNotFoundError` 失败，再实现 `challenge.py`，3 用例全部通过；`arena` 全部 7 个测试（含 Task2 的 world 测试）无回归。未新增额外字段/功能（YAGNI）。commit: 2070fe0。
