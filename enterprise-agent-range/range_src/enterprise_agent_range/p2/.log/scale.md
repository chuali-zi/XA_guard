# scale.py 工作日志

2026-07-02 实现 P2 能力 7（大规模自动化 red-team runner 分片器）。

- `Sharder.shard(plan)`：读取 `plan.manifest_path` JSON manifest，取
  `cases[].case_id` 去重排序，用 `sha256(f"{seed}:{case_id}") % shard_count`
  分桶，保证固定 (manifest, seed, shard_count) → 固定分片结果。
  `shard_count<1` 抛 `ValueError`；manifest 不存在抛 `FileNotFoundError`。
- 新增模块级 `verify_partition(plan, shards)`：校验分片是并集覆盖全部
  case_id、无重复、无遗漏的真分区。
- `SPEC.status` 改为 `IMPLEMENTED`。
- 未改动 `base.py`/`registry.py`/其它 runtime 模块；未 import xa_guard。
- 新增 `tests/test_p2_scale.py`：分区正确性、确定性、shard_count 边界、
  manifest 缺失、shard_count 大于 case 数（空分片）等用例，全部通过。
