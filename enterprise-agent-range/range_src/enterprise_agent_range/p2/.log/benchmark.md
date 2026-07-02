# benchmark.py 工作日志

2026-07-02 实现 P2 能力 8（外部 benchmark 与内部靶场融合，仅离线）。

- `BenchmarkAdapter.load(source, path)`：本地 JSON 文件（list of
  `{external_case_id, outcome, ...}`），无任何网络调用；缺失文件抛
  `FileNotFoundError`，非 list 抛 `ValueError`。用模块常量
  `OUTCOME_TAXONOMY_MAP`（agentdojo/injecagent 两个示例 source）把 outcome
  映射到靶场 taxonomy，未知 outcome/source 一律映射到 `("UNKNOWN",)`；结果按
  (source, external_case_id) 排序，保证确定性。
- `BenchmarkAdapter.fuse(records, case_results)`：返回
  internal_count/external_count/fused_case_count/by_source/
  taxonomy_coverage（内部 case 的 taxonomy 字段 + 外部映射taxonomy 合并计数，
  key 排序输出）。
- `SPEC.status` 改为 `IMPLEMENTED`。未改其它文件，未 import xa_guard。
- 新增 `tests/test_p2_benchmark.py`：load 映射已知/未知 outcome、metadata
  保留、fuse 计数与 taxonomy_coverage、确定性、空输入，全部通过。
