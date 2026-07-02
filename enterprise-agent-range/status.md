# Enterprise Agent Range 状态

> 快照日期：2026-07-02 01:51 PDT
> 本状态只描述 `enterprise-agent-range/` 独立靶场，不描述 XA-Guard 主产品状态。

## 当前结论

`main` 已按堆叠顺序 fast-forward 合并 `codex/enterprise-range-p1` 与 `codex/enterprise-range-p2`，当前 HEAD 为 `b696244`。当前目录包含独立 Python runtime、P0/P1 case manifest、synthetic fixtures、66 个 mock tool、Null Adapter、oracle/metrics、JSON/JSONL/Markdown/HTML 报告、baseline-vs-candidate compare 输出、MCP-like stdio、本地 MCP-like HTTP、simulated IDE replay，以及 P2 研究级能力子包。靶场仍与 XA-Guard 产品代码解耦：未导入 `src/xa_guard`，未把 runtime 放入父仓库 `src/`，未复用 XA-Guard bench/schema/helper。

最新 P1 本地验收使用 Null Adapter 跑完 `cases/p1_manifest.json`，输出在 `reports/run-p1-null-verify/`：242 个 case 全部有效，`INFRA_ERROR=0`，`INVALID=0`，run-level audit hash chain valid。Null Adapter 是无防护基线，attack case 的 FAIL 是预期暴露风险，不代表任何外部 SUT 的评测结论。

P2 review finding 已修复并进入 `main`：`permissions` 授权校验现在拒绝 `issued_at` 之前的使用；`remediation` 对重复 `payload_hash` 的 side-effect 生成稳定且不冲突的 `action_id`。合并后全量 `python -m unittest discover -s tests` 为 203 tests PASS。P2 仍未接入 runner/oracle/metrics/report；下一步应推进 P2 case、fixture、oracle/metrics 和报告集成。

## P2 能力实现（2026-07-02）

P2 研究级靶场先搭骨架，再由 5 个并行子 agent（一 agent 负责一对相关能力，严格文件隔离）实现全部 10 个能力模块。独立子包 `range_src/enterprise_agent_range/p2/` 含能力注册表和 10 个能力模块，每个模块现有真实、确定性、仅依赖 stdlib 的逻辑 + frozen dataclass + 独立单测：

- tenancy：租户注册 + 按租户隔离视图 + 跨租户泄漏检测。
- discovery：声明清单 vs 观测清单 diff，输出 Shadow AI 发现。
- identity：Agent 身份生命周期状态机（provision/active/rotate/suspend/revoke/retire）+ `can_act` 门禁。
- permissions：JIT/JEA/JLA 授予签发与校验（整数 epoch 时间、scope 子集、过期/撤销拒绝、签发前拒绝）。
- risk：按权重表量化合成风险金额（`RANGE` 单位，非真实货币）。
- remediation：对已提交副作用给出补偿/undo 建议（仅建议，不执行）；`action_id` 已基于稳定 side-effect 行身份生成，避免重复 payload hash 跨 trace 撞 ID。
- scale：确定性 manifest 分片（sha256 分桶，真分区）。
- benchmark：离线外部 benchmark 载入 + 与内部结果融合（无网络）。
- evidence：mock TSA/HSM 的 HMAC 签发与校验（假密钥、可检测篡改）。
- dashboard：从 run 输出只读构建大屏 feed 与复盘报告对象。

边界不变：P0/P1 runtime 与 oracle 仍零改动；p2 只依赖 `.base` + stdlib，无 `import xa_guard`、无核心运行时耦合。唯一改动的既有文件仍是 `cli.py`（`p2-status` 子命令 + UTF-8 stdout 兜底）。计划中的 P2 oracle/metrics 字段记录在 `p2/schema.py`，尚未接入现有 oracle（不影响 manifest 校验）。设计文档见 `docs/superpowers/specs/2026-07-02-p2-scaffolding-design.md`。

验证：`python -m unittest discover -s tests` 203 tests PASS（含 P2 review finding 回归）；`PYTHONPATH=range_src python -m enterprise_agent_range p2-status --json` 10 项均为 `implemented`；`PYTHONPATH=range_src python -m enterprise_agent_range validate --manifest cases/p1_manifest.json` 仍 242 cases / 44 fixtures，输出不变。

未做（下一步）：把各能力接入 runner/oracle/metrics/report（新增 oracle handler 与风险加权指标）、编写真实 P2 case 与 fixture、生成大屏/复盘产物文件、多能力联动（identity↔permissions、risk↔remediation）。

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
| `python -m unittest discover -s tests` | PASS，203 tests |
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
