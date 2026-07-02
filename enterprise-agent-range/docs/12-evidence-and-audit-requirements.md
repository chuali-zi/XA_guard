# 证据与审计要求

## 证据目标

每个 case 都必须能回答：

1. 谁发起了任务。
2. 哪个 Agent 执行。
3. 使用了哪些输入和数据源。
4. 调用了哪些工具。
5. SUT 做了什么决策。
6. 下游是否发生副作用。
7. 敏感数据是否外泄。
8. 审计是否完整且不可篡改。
9. 结果能否复现和重算。

## 证据目录结构

后续实现建议每次运行输出：

```text
reports/<run_id>/
├── run-manifest.json
├── environment.json
├── case-results.jsonl
├── side-effects.jsonl
├── audit-records.jsonl
├── metrics.json
├── report.md
├── artifact-hashes.json
└── raw/
```

## run-manifest 必填

| 字段 | 说明 |
|---|---|
| `run_id` | 唯一运行 ID。 |
| `started_at` | ISO 8601 时间。 |
| `range_version` | 靶场版本或 commit。 |
| `case_manifest_hash` | case manifest hash。 |
| `sut_id` | 被测系统 ID。 |
| `sut_adapter` | adapter 类型。 |
| `operator` | 执行者或 CI 标识。 |
| `mode` | local / sut / redteam / regression。 |

## environment 必填

| 字段 | 说明 |
|---|---|
| `os` | 操作系统。 |
| `python_version` | Python 版本，若使用。 |
| `container_runtime` | Docker / podman / none。 |
| `network_mode` | offline / local-only / controlled-egress。 |
| `timezone` | 时区。 |
| `seed` | 随机种子。 |
| `dirty_state` | 工作区状态。 |

## case-result 必填

| 字段 | 说明 |
|---|---|
| `case_id` | case ID。 |
| `trace_id` | trace ID。 |
| `case_kind` | attack / benign / assurance。 |
| `taxonomy` | 攻击分类。 |
| `expected` | 期望 oracle。 |
| `actual` | 实际结果。 |
| `status` | PASS / FAIL / INFRA_ERROR 等。 |
| `latency_ms` | 延迟。 |
| `evidence_refs` | 原始证据路径。 |

## side-effect 必填

| 字段 | 说明 |
|---|---|
| `trace_id` | trace ID。 |
| `sink_type` | mail / notification / http / ticket / command / plugin / payment。 |
| `operation` | 操作。 |
| `payload_hash` | 载荷 hash。 |
| `sensitive_hits` | 命中的敏感模式。 |
| `committed` | 是否发生副作用。 |

## 审计要求

审计记录至少应支持：

1. 字段完整性检查。
2. hash manifest。
3. 记录顺序检查。
4. trace_id 关联。
5. case_id 关联。
6. SUT response 关联。
7. 下游副作用关联。
8. 重放一致性检查。

## hash 要求

每次运行必须生成 `artifact-hashes.json`，覆盖：

1. case manifest。
2. fixture 文件。
3. SUT adapter 配置。
4. 运行环境记录。
5. 原始 case result。
6. side effect log。
7. audit records。
8. metrics。
9. final report。

## 人工证据要求

人工 case 必须包含：

1. 步骤。
2. 截图或录像路径。
3. 版本信息。
4. 时间。
5. 操作者。
6. 为什么不能自动化。
7. 后续自动化条件。

人工证据不得混入自动化指标分母。
