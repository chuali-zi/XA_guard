# Enterprise Agent Range 工作日志

## 2026-07-01 08:39 PDT

根据 review 修复 P0 靶场评测可信度问题。已完成：`oracles.py` 增加 `SUPPORTED_EXPECTED_FIELDS` 和 handler registry，当前 manifest 中全部 `expected` 字段均有机器判定，未知 expected 字段会在 validation 阶段报错；修复 per-case audit segment 校验，第二个 case 之后不再因全局 hash chain 起点不同被误判；新增 run-level audit integrity 指标；修复 `list_traces`，支持 `trace_id`、`case_id`、`sink` 过滤；父仓库 `.gitignore` 增加 scoped 例外，使 `reports/run-p0-null-verify/*.jsonl` 原始证据可被提交。

已补测试：manifest 未知 expected 字段、描述性 oracle 缺机器字段、审计链 segment、oracle 代表项（审批、供应链、审计、委托、数据外泄、沙箱）和 trace 过滤。验证通过：`python -m compileall range_src`、`python -m unittest discover -s tests`（12 tests）、`python -m enterprise_agent_range validate --manifest cases/p0_manifest.json`、`python -m enterprise_agent_range run --manifest cases/p0_manifest.json --out reports --run-id run-p0-null-verify --adapter null_adapter --sut-id null-baseline --mode local --operator codex`。最新 run：84 valid、0 infra error、0 invalid、audit integrity 1.0。

未完成：仍未实现真实 CLI/HTTP/MCP stdio SUT adapter、MCP mock server、前端可视化、容器编排和 P1 扩展。Null Adapter 仍只是无防护基线。

## 2026-07-01 07:35 PDT

根据 `docs/` 的 P0 要求，将 `enterprise-agent-range/` 从设计文档推进到可运行骨架。新增 `pyproject.toml`、`range_src/enterprise_agent_range/` runtime、`cases/p0_manifest.json`、`fixtures/`、`tests/` 和 `reports/run-p0-null-verify/`。runtime 包含模型、fixture loader、25 个 MCP-like mock tool、Null Adapter、oracle/metrics、报告生成和 CLI；mock 写操作只进入本地 synthetic sink，`exec_command` 只记录不执行真实 shell。通过子 agent 填充 P0 语料后，由主线程完成验收和兼容修补。

已完成：84 个 P0 case（38 attack、36 benign、10 assurance）、27 个 synthetic fixture、8 条攻击/验证链、JSON/JSONL/Markdown 证据包输出和最小测试。验证命令包括 `python -m compileall range_src`、`python -m unittest discover -s tests`、`python -m enterprise_agent_range validate --manifest cases/p0_manifest.json`、`python -m enterprise_agent_range run --manifest cases/p0_manifest.json --out reports --run-id run-p0-null-verify --adapter null_adapter --sut-id null-baseline --mode local --operator codex`，结果为 84 valid、0 infra error、0 invalid。

未完成：真实 CLI/HTTP/MCP stdio SUT adapter、MCP mock server、前端可视化、容器编排和 P1 规模扩展。当前 Null Adapter 只是无防护基线，attack case 的 FAIL 代表基线暴露风险，不代表任何外部 SUT 已通过或失败。

## 2026-07-01

创建 `enterprise-agent-range/` 独立靶场设计区，落地设计说明、范围、架构、资产、角色、工具面、攻击分类、场景矩阵、指标、证据、路线、风险、数据模型和数据流文档。当前仅为文档设计，未实现运行时代码，未耦合 `src/xa_guard` 或既有 `docs/`。
