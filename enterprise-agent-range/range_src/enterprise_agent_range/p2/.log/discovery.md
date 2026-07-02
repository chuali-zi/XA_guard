# discovery.py 工作日志

2026-07-02：将 `DiscoveryScan` 从纯桩实现为确定性 Shadow AI 发现逻辑。

- `scan(inventory)`：输入 `{"declared_agents": [...], "declared_tools": [...], "observed": [{"kind": "agent"|"tool", "id": ..., "evidence"?: ...}]}`。
- observed 中 id 不在对应 declared 集合内的行生成 `ShadowFinding`：
  - kind="agent" 未声明 -> `unregistered_agent` / severity=high
  - kind="tool" 未声明 -> `unapproved_plugin` / severity=medium
- `evidence_ref` 优先取行内 `evidence` 字段，否则合成 `observed:{kind}:{id}`。
- 未知 kind 的观测行被忽略（无对应声明集合可比对）。
- 结果按 `(finding.kind, finding.finding_id)` 排序，保证确定性输出，无 datetime/random。
- `SPEC.status` 置为 `CapabilityStatus.IMPLEMENTED`。

未改动其他公共文件，未 import xa_guard 或其他 P2 模块。新增测试 `tests/test_p2_discovery.py` 覆盖声明命中忽略、未声明告警、evidence 合成、未知 kind、排序确定性等场景。
