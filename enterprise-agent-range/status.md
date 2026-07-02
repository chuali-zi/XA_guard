# Enterprise Agent Range 状态

> 快照日期：2026-07-01
> 本状态只描述 `enterprise-agent-range/` 独立靶场，不描述 XA-Guard 主产品状态。

## 当前结论

P0 已从纯设计文档推进到可运行的独立靶场骨架。当前仓库包含独立 Python runtime、P0 case manifest、synthetic fixtures、mock tool surface、Null Adapter、oracle/metrics、报告证据包和最小测试。靶场仍与 XA-Guard 产品代码解耦：未导入 `src/xa_guard`，未把 runtime 放入根 `src/`，未复用 XA-Guard bench/schema/helper。

最近一次本地验收使用 Null Adapter 跑完 `cases/p0_manifest.json`，输出在 `reports/run-p0-null-verify/`：84 个 case 全部有效，`INFRA_ERROR=0`，`INVALID=0`，run-level audit hash chain valid。Null Adapter 是无防护基线，attack case 的 FAIL 是预期暴露风险，不代表 runtime 失败。

## 已完成

| 项 | 状态 | 说明 |
|---|---|---|
| 设计文档 | DONE | `docs/` 已覆盖目标范围、企业场景、架构、工具面、攻击矩阵、指标、证据、数据模型和数据流。 |
| Runtime 骨架 | DONE | 新增 `range_src/enterprise_agent_range/`，包含模型、fixture loader、tool surface、adapter、runner、oracle、report writer 和 CLI。 |
| Mock 工具面 | DONE | 覆盖 25 个 MCP-like mock tool，写操作只进入本地 synthetic sink；`exec_command` 只记录不执行真实 shell。 |
| P0 case 语料 | DONE | `cases/p0_manifest.json` 包含 38 个 attack case、36 个 benign control、10 个 assurance check。 |
| Fixture 语料 | DONE | `fixtures/` 包含 27 个 synthetic fixture，覆盖 mail、RAG、logs、plugins、audit、data、policies。 |
| 攻击链 | DONE | manifest 包含 8 条链路，覆盖会议纪要污染外发、日志注入、供应链、委托越权、BEC 付款、审计篡改、审批绕过和 RAG 注入。 |
| Runner 与证据包 | DONE | 可输出 `run-manifest.json`、`environment.json`、`case-results.jsonl`、`side-effects.jsonl`、`audit-records.jsonl`、`metrics.json`、`report.md`、`artifact-hashes.json`。 |
| Oracle 覆盖 | DONE | 当前 P0 manifest 中所有 `expected` 字段都有机器判定；未知 expected 字段会在 manifest validation 阶段报错。 |
| 审计链校验 | DONE | 支持 per-case audit segment 校验和 run-level audit chain integrity 指标，避免第二个 case 起误判。 |
| Trace 查询 | DONE | `list_traces` 支持按 `trace_id`、`case_id`、`sink` 过滤，`expect_count` 只基于过滤结果。 |
| 最小测试 | DONE | `tests/` 覆盖 runner smoke、manifest validation、oracle 代表项、trace 过滤、工具面数量和 `exec_command` 只记录不执行。 |

## 验收结果

| 命令 | 结果 |
|---|---|
| `python -m compileall range_src` | PASS |
| `python -m unittest discover -s tests` | PASS，12 tests |
| `python -m enterprise_agent_range validate --manifest cases/p0_manifest.json` | PASS，84 cases / 27 fixtures；fixture hash 为 pending warning，runner 会重算 artifact hash |
| `python -m enterprise_agent_range run --manifest cases/p0_manifest.json --out reports --run-id run-p0-null-verify --adapter null_adapter --sut-id null-baseline --mode local --operator codex` | PASS，84 valid / 0 infra error / 0 invalid；audit integrity 1.0 |

## 最新指标

| 指标 | 值 |
|---|---|
| Total / Valid cases | 84 / 84 |
| PASS / FAIL / INFRA_ERROR / INVALID | 43 / 41 / 0 / 0 |
| Attack Success Rate | 0.947368 |
| False Positive Rate | 0.0 |
| Utility Retention | 1.0 |
| Data Exposure Rate | 0.333333 |
| Audit Completeness | 1.0 |
| Audit Integrity | 1.0 |

## 证据提交状态

`reports/run-p0-null-verify/` 作为 P0 固定验收包保留。父仓库 `.gitignore` 已添加 scoped 例外，使 `case-results.jsonl`、`side-effects.jsonl`、`audit-records.jsonl` 可被 git 跟踪；`artifact-hashes.json` 覆盖这些 JSONL 原始证据文件。

## 未完成

| 项 | 状态 | 下一步 |
|---|---|---|
| 外部 SUT adapter | TODO | 实现 CLI/HTTP/MCP stdio adapter，把 XA-Guard 或其他防护系统作为外部进程/服务接入。 |
| 真实 MCP 协议暴露 | TODO | 将当前 in-process tool surface 包装为 stdio 或 HTTP MCP mock server。 |
| P1 扩展规模 | TODO | 扩展到 100+ attack case、100+ benign control、更多业务域和多 Agent 委托链。 |
| 前端可视化 | TODO | 后续实现独立报告 UI，不复用 XA-Guard frontend。 |
| 容器编排 | TODO | 后续补本地离线容器运行模式和可重复环境封装。 |

## 强边界

- 不攻击真实公网目标。
- 不使用真实个人隐私数据。
- 不放真实密钥。
- 不连接生产 API。
- 不执行真实破坏性命令。
- 不把 Null Adapter 基线结果表述为任何 SUT 已通过评测。
