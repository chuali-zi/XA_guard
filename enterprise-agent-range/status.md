# Enterprise Agent Range 状态

> 快照日期：2026-07-01 21:16 PDT
> 本状态只描述 `enterprise-agent-range/` 独立靶场，不描述 XA-Guard 主产品状态。

## 当前结论

P1 已完成 review 修复后的本地基线：当前目录包含独立 Python runtime、P0/P1 case manifest、synthetic fixtures、66 个 mock tool、Null Adapter、oracle/metrics、JSON/JSONL/Markdown/HTML 报告、baseline-vs-candidate compare 输出、MCP-like stdio、本地 MCP-like HTTP 和 simulated IDE replay。靶场仍与 XA-Guard 产品代码解耦：未导入 `src/xa_guard`，未把 runtime 放入父仓库 `src/`，未复用 XA-Guard bench/schema/helper。

最新 P1 本地验收使用 Null Adapter 跑完 `cases/p1_manifest.json`，输出在 `reports/run-p1-null-verify/`：242 个 case 全部有效，`INFRA_ERROR=0`，`INVALID=0`，run-level audit hash chain valid。Null Adapter 是无防护基线，attack case 的 FAIL 是预期暴露风险，不代表任何外部 SUT 的评测结论。

## P2 脚手架（2026-07-02）

P2 研究级能力已搭好纯骨架，尚未实现任何真实逻辑。新增独立子包 `range_src/enterprise_agent_range/p2/`，含能力注册表和 10 个能力模块（多租户、Shadow AI 发现、Agent 身份生命周期、JIT/JEA/JLA 权限、风险金额量化、Undo/补偿、大规模 red-team runner、外部 benchmark 融合、TSA/HSM 证据、攻防大屏复盘），每个模块只有 frozen dataclass 数据结构和接口桩，调用抛 `P2NotImplementedError`。P0/P1 runtime 与 oracle 零改动；唯一改动的既有文件是 `cli.py`（新增 `p2-status` 子命令，并为非 ASCII 输出加 UTF-8 stdout 兜底）。计划中的 P2 oracle/metrics 字段记录在 `p2/schema.py`，尚未接入现有 oracle（不影响 manifest 校验）。另新增 `cases/p2_manifest.example.json` 模板、`fixtures/p2/README.md` 占位、`tests/test_p2_scaffold.py`。设计文档见 `docs/superpowers/specs/2026-07-02-p2-scaffolding-design.md`。

验证：`python -m unittest discover -s tests` 41 tests PASS；`python -m enterprise_agent_range p2-status` 列出 10 项能力；`validate --manifest cases/p1_manifest.json` 仍 242 cases / 44 fixtures，输出不变。

## 已完成

| 项 | 状态 | 说明 |
|---|---|---|
| 设计文档 | DONE | `docs/` 已覆盖目标范围、企业场景、架构、工具面、攻击矩阵、指标、证据、数据模型和数据流。 |
| Runtime 骨架 | DONE | `range_src/enterprise_agent_range/` 包含模型、fixture loader、tool surface、adapter、runner、oracle、report writer、协议层和 CLI。 |
| Mock 工具面 | DONE | 覆盖 66 个 MCP-like mock tool，包含 P0 工具和 P1 的 calendar/tasks、HR、finance、operations/release、customer/ticket/business API、repo/dependency/artifact、plugin review/quarantine、agent registry/delegation/capability grant、policy-copy mutation；写操作只进入本地 synthetic sink；`exec_command` 只记录不执行真实 shell。 |
| P0 case 语料 | DONE | `cases/p0_manifest.json` 包含 38 个 attack case、36 个 benign control、10 个 assurance check。 |
| P1 case 语料 | DONE | `cases/p1_manifest.json` 包含 108 个 attack case、116 个 benign control、18 个 assurance check，覆盖原六域，并补充 calendar/tasks、HR、customer、repo/artifact、agent governance 的工具面覆盖 case。 |
| P1 工具覆盖 | DONE | P1 execution steps 已覆盖全部 66 个 `TOOL_DEFINITIONS`，由 `tests/test_tool_surface.py` 回归锁定。 |
| P1 fixture 语料 | DONE | `fixtures/p1/` synthetic fixture 覆盖办公污染、HR/客户/财务数据、BEC 邮件、运维/CI 日志、供应链 AIBOM、审计篡改、委托链和 IDE extension 样本。 |
| 多 surface 分层 | DONE | P1 manifest 覆盖 `sut_adapter`、`mcp_stdio`、`mcp_http`、`simulated_ide`；metrics 输出 `strata.domain`、`strata.surface`、`strata.case_kind`。 |
| 多 Agent 委托证据 | DONE | 20 个委托相关 P1 case 均有显式 `delegation_chain`；`build_actual` 输出 chain、depth、original principal present，oracle 可区分完整链与缺 original principal。 |
| Fixture 路径边界 | DONE | fixture ref 解析拒绝绝对路径、`..` traversal 和解析后越出 manifest root 的路径；direct tool 和 protocol 调用均有回归测试。 |
| Mutation engine | DONE | `mutations.py` 提供确定性文本变体生成，当前用于后续 case 变体扩展，不引入随机不可复现结果。 |
| 本地协议面 | DONE | `protocol.py` 提供统一请求处理；CLI 暴露 `serve-stdio`、`serve-http`、`ide-replay`；HTTP 仅允许绑定本地地址，工具调用仍通过 `execute_tool`、`RangeState` 和 synthetic sinks。 |
| Runner 与证据包 | DONE | 可输出 `run-manifest.json`、`environment.json`、`case-results.jsonl`、`side-effects.jsonl`、`audit-records.jsonl`、`metrics.json`、`report.md`、`report.html`、`artifact-hashes.json`。 |
| Compare 报告 | DONE | CLI `compare` 可读取两个 run 目录，输出 `compare.json`、`compare.md`、`compare.html`；本轮已重生成 `reports/compare-p0-p1-null/`。 |
| Oracle 覆盖 | DONE | 当前 P0/P1 manifest 使用的 `expected` 字段都有机器判定；未知 expected 字段会在 validation 阶段报错。 |
| 审计链校验 | DONE | 支持 per-case audit segment 校验和 run-level audit chain integrity 指标。 |
| Trace 查询 | DONE | `list_traces` 支持按 `trace_id`、`case_id`、`sink` 过滤，`expect_count` 只基于过滤结果。 |
| 测试 | DONE | `tests/` 覆盖 runner smoke、manifest validation、oracle、trace 过滤、工具面数量/元数据、P1 tool coverage、delegation evidence、protocol path boundary、IDE replay、HTML escaping、compare 输出和 mutation 核心逻辑。 |

## 验收结果

> 本地源码树未安装为 editable package；以下 `enterprise_agent_range` CLI 命令均在 `PYTHONPATH=range_src` 下运行。

| 命令 | 结果 |
|---|---|
| `python -m compileall range_src` | PASS |
| `python -m unittest discover -s tests` | PASS，30 tests |
| `python -m enterprise_agent_range validate --manifest cases/p0_manifest.json` | PASS，84 cases / 27 fixtures；fixture hash 为 pending warning，runner 会重算 artifact hash |
| `python -m enterprise_agent_range validate --manifest cases/p1_manifest.json` | PASS，242 cases / 44 fixtures；fixture hash 为 pending warning，runner 会重算 artifact hash |
| `python -m enterprise_agent_range run --manifest cases/p1_manifest.json --out reports --run-id run-p1-null-verify --adapter null_adapter --sut-id null-baseline --mode local --operator codex` | PASS，242 valid / 0 infra error / 0 invalid；audit integrity 1.0 |
| `python -m enterprise_agent_range compare --baseline reports/run-p0-null-verify --candidate reports/run-p1-null-verify --out reports/compare-p0-p1-null` | PASS，生成 compare JSON/Markdown/HTML |

## 最新 P1 指标

| 指标 | 值 |
|---|---|
| Total / Valid cases | 242 / 242 |
| Attack / Benign / Assurance | 108 / 116 / 18 |
| PASS / FAIL / INFRA_ERROR / INVALID | 136 / 106 / 0 / 0 |
| Attack Success Rate | 0.888889 |
| False Positive Rate | 0.0 |
| Utility Retention | 1.0 |
| Data Exposure Rate | 0.25 |
| Audit Completeness | 1.0 |
| Audit Integrity | 1.0 |
| Surface strata | `sut_adapter`: 180；`simulated_ide`: 41；`mcp_http`: 13；`mcp_stdio`: 8 |

## 证据提交状态

- P0 固定验收包保留在 `reports/run-p0-null-verify/`。
- P1 验收包在 `reports/run-p1-null-verify/`，包含 JSON/JSONL/Markdown/HTML 和 artifact hashes。
- P0 vs P1 Null Adapter 对比包在 `reports/compare-p0-p1-null/`，包含 `compare.json`、`compare.md`、`compare.html`。

## 未完成

| 项 | 状态 | 下一步 |
|---|---|---|
| 外部 SUT adapter | TODO | 实现 CLI/HTTP/MCP stdio adapter，把 XA-Guard 或其他防护系统作为外部进程/服务接入，并把 SUT 决策映射为靶场 actual。 |
| 标准 MCP 兼容性 | TODO | 当前是本地 MCP-like JSON-lines/HTTP 安全协议面；如需严格 MCP JSON-RPC/schema，需要补兼容层和协议 fixtures。 |
| 交互式报告 UI | TODO | 目前已有静态 HTML run/compare 报告；若需要筛选、排序、趋势图，再实现独立报告 UI，不复用 XA-Guard frontend。 |
| 容器编排 | TODO | 后续补本地离线容器运行模式和可重复环境封装。 |
| 外部真实验收 | TODO | 尚未接真实 Trae、真实外部 SUT、真实 HSM/TSA 或生产 API。 |

## 强边界

- 不攻击真实公网目标。
- 不使用真实个人隐私数据。
- 不放真实密钥。
- 不连接生产 API。
- 不执行真实破坏性命令。
- 不把 Null Adapter 基线结果表述为任何 SUT 已通过评测。
