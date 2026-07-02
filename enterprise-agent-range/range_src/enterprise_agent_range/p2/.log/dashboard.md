# dashboard.py 工作日志

2026-07-02：将 `DashboardBuilder` 从纯桩实现为读取既有 run 输出并组装数据对象的确定性逻辑，不写任何文件。

- `build_feed(run_dir, generated_at="")`：读取 `metrics.json`/`case-results.jsonl`；`run_id` 取 `metrics.json.run_id`，缺失则回退目录名；`headline_metrics` 摘取关键指标+`counts`；`timeline` 按 `case_kind` 排序统计每类 `pass`/`fail`。
- `build_review(run_dir)`：`findings` 收集 `attack_case` 且 `status=="FAIL"`、以及 `benign_control` 且 `status=="FAIL"`（误报）两类行，按 `case_id` 排序，字段含 case_id/case_kind/status/title；`summary` 含关键数字；`evidence_index` 固定映射到 metrics/case_results/audit/side_effects/report_md 五个文件名。
- 任一必需文件缺失抛 `FileNotFoundError` 并附清晰信息。

仅用 pathlib+json（stdlib），未改动 `base.py`/`registry.py`，未 import xa_guard 或其他 P2/核心 runtime 模块，未读写 `reports/` 之外内容。新增 `tests/test_p2_dashboard.py`：临时目录构造 metrics.json + 4 行 case-results.jsonl，覆盖 headline/timeline/findings/evidence_index/run_id 回退/确定性/缺文件异常。
