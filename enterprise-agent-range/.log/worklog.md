# 2026-07-02 20:06 -07:00 Enterprise Agent Range Arena Core / 红队台实现

- 按用户确认的方向执行重构：优先做 Arena Core 解耦与红队成员工作台地基，不优先扩题，不替红队成员设计攻击题。
- 使用 3 个 gpt-5.5 medium 子 agent 协助并整合结果：证据核心、tool surface/policy overlay、redteam finding 工作流；主线程完成 live runner 集成、CLI `arena` 命令组、测试补齐和状态文档收口。
- 新增/整合 Arena Core 模块：`arena/worlds.py`、`suite.py`、`surface.py`、`policy_overlay.py`、`evidence.py`、`opencode_seat.py`、`sut_xaguard.py`、`findings.py`；`challenge.py` 增加可选 `PolicySpec`；`mcp_office_server.py` 复用 tool surface schema；`live.py` 接入 `EvidenceStore` 并继续兼容既有 live smoke 行为。
- CLI 新增最小红队台：`python -m enterprise_agent_range arena worlds|surfaces|challenges|init-finding|promote|show|run-ab`；旧 `arena-live`、`finding-init`、`finding-promote` 保持兼容，并给 `arena-live` 增加 `--suite`。
- 新增测试：`test_arena_cli.py`、`test_arena_evidence.py`、`test_arena_findings.py`、`test_arena_opencode_and_sut.py`、`test_arena_policy_overlay.py`、`test_arena_surface.py`、`test_arena_worlds_and_suite.py`，并扩展 `test_arena_live.py` 验证 mocked null attempt 会写 `artifact-hashes.json`。
- 验证：`$env:PYTHONPATH='range_src'; python -m unittest discover -s tests -v` 通过 263 tests；受影响 arena 子集 30 tests 通过；`arena worlds --json`、`arena surfaces --json` CLI smoke 通过；`validate --manifest cases\p1_manifest.json` 通过 242 cases / 44 fixtures；`rg "from xa_guard|import xa_guard" enterprise-agent-range\range_src\enterprise_agent_range` 无匹配。
- 未做：未运行真实 OpenCode/GLM live 模型调用；未修改根 `src/xa_guard`；未把旧 242 个 P1 case 迁移到 live challenge schema；未实现 live attempt/report -> regression promotion、live N 次统计或多企业域扩展。
## 2026-07-02 19:05 PDT docs 重构与 redteam arena plan

清理 `docs/`：删除旧 00-17 编号文档和 `docs/superpowers/` 工作流目录；新增 `docs/README.md`、`docs/plan/redteam-arena-refactor-plan.md`、`docs/architecture/`、`docs/redteam/`、`docs/reference/`。计划明确下一步优先 Arena Core 解耦与红队工作台地基，不优先扩题。未改 runtime、case、测试或报告证据；等待用户审核 plan 后再动代码。
# Enterprise Agent Range 工作日志

## 2026-07-02（P2 能力实现）

在 P2 脚手架基础上，push 分支后派 5 个 sonnet 并行子 agent 实现全部 10 个能力（一 agent 一对相关能力，严格文件隔离：只改自己两个模块 + 自建单测 + 各自 `p2/.log/*.md`）。tenancy/discovery/identity/permissions/risk/remediation/scale/benchmark/evidence/dashboard 均从接口桩替换为真实、确定性、仅 stdlib 逻辑，`SPEC.status` 置 `implemented`。主线程先放宽 `test_p2_scaffold` 的"全是桩"断言，集成后跑全量：199 tests PASS（40 结构 + 159 能力单测），`p2-status` 全 `implemented`，`validate p1` 仍 242/44 不变，p2 无 `xa_guard`/核心运行时耦合。未做：接入 runner/oracle/metrics/report、真实 P2 case/fixture、大屏产物、能力联动。

## 2026-07-02

搭建 P2 研究级靶场脚手架（纯骨架，经 brainstorming 确认：新建 p2/ 子包 + 全部 10 项建桩）。新建 `range_src/enterprise_agent_range/p2/`：base、registry(10 项)、schema(计划中 expected/metrics，未接入 oracle)，及 tenancy/discovery/identity/permissions/risk/remediation/scale/benchmark/evidence/dashboard 十个模块（dataclass + 接口桩，调用均抛 `P2NotImplementedError`）。`cli.py` 新增 `p2-status` 子命令 + UTF-8 stdout 兜底。新增 `cases/p2_manifest.example.json` 模板、`fixtures/p2/README.md` 占位、`tests/test_p2_scaffold.py`。P0/P1 runtime 与 oracle 零改动。验证：compileall PASS；unittest 41 tests PASS；`p2-status` 文本/JSON 均列出 10 项；`validate p1` 仍 242 cases/44 fixtures 不变。未做：任何 P2 真实逻辑与数据、真实 TSA/HSM/benchmark。

## 2026-07-01 21:16 PDT

按 P1 review fix 计划修复三个问题：fixture 路径越界、P1 manifest 未覆盖新增工具、委托链 oracle 缺少显式证据。使用子 agent 协助：Worker C 写 protocol/path traversal 测试，Worker A 只读梳理 44 个未覆盖工具，Worker B 只读梳理 20 个委托相关 case；主线程完成 runtime 修复、manifest 集成、测试和证据重生成。

已完成：`tools.py` 的 fixture ref 解析拒绝绝对路径、`..` traversal 和解析后越出 manifest root 的路径；`protocol.py` 通过同一路径安全返回 bad request；`cases/p1_manifest.json` 更新为 242 cases（108 attack、116 benign、18 assurance），P1 execution steps 覆盖全部 66 个 mock tool；20 个委托相关 case 补齐 `delegation_chain`；`build_actual` 输出 chain，并用显式 `original_principal` 判断 original principal preservation；新增路径穿越、工具覆盖和委托链证据回归测试；重生成 `reports/run-p1-null-verify/` 和 `reports/compare-p0-p1-null/`；同步 README、status 和日志。

验证通过：`python -m compileall range_src`；`python -m unittest discover -s tests`（30 tests）；`PYTHONPATH=range_src python -m enterprise_agent_range validate --manifest cases/p0_manifest.json`；`PYTHONPATH=range_src python -m enterprise_agent_range validate --manifest cases/p1_manifest.json`；`PYTHONPATH=range_src python -m enterprise_agent_range run --manifest cases/p1_manifest.json --out reports --run-id run-p1-null-verify --adapter null_adapter --sut-id null-baseline --mode local --operator codex`（242 valid / 0 infra error / 0 invalid，FPR 0.0，utility 1.0，audit integrity 1.0）；P0/P1 compare CLI。

未完成：真实外部 SUT adapter、严格 MCP schema 兼容层、交互式报告 UI、容器编排、真实 Trae、真实 HSM/TSA 和生产 API 接入。Null Adapter 仍是无防护基线，attack case 失败不代表任何外部 SUT 的评测结论。

## 2026-07-01 19:44 PDT

按用户要求实施 P1 企业完整靶场扩展。执行顺序：先在父仓库提交并推送当前全部改动（commit `85ea632`，已推送 `main` 到 `origin/main`），再创建并切换到 `codex/enterprise-range-p1` 分支。随后使用 4 个 gpt-5.5 medium worker 子 agent 分工：Worker A 扩展 P1 case/fixture，Worker B 扩展 tool surface，Worker C 实现本地协议面，Worker D 实现 HTML/compare 报告；主线程负责接口收口、冲突检查、验证和状态维护。

已完成：新增 `cases/p1_manifest.json`，含 108 attack、108 benign、18 assurance，总计 234 个 case；新增 `fixtures/p1/` synthetic fixture；tool surface 扩展到 66 个工具并补齐能力/审批/数据级别元数据；新增 `protocol.py` 和 CLI `serve-stdio`、`serve-http`、`ide-replay`；新增 `mutations.py`；新增 HTML run report、compare helper 和 CLI `compare`；生成 `reports/run-p1-null-verify/` 与 `reports/compare-p0-p1-null/`；更新 README、status 和日志。

验证通过：`python -m compileall range_src`；`python -m unittest discover -s tests`（25 tests）；`python -m enterprise_agent_range validate --manifest cases/p0_manifest.json`；`python -m enterprise_agent_range validate --manifest cases/p1_manifest.json`；`python -m enterprise_agent_range run --manifest cases/p1_manifest.json --out reports --run-id run-p1-null-verify --adapter null_adapter --sut-id null-baseline --mode local --operator codex`（234 valid / 0 infra error / 0 invalid，audit integrity 1.0）；stdio `tools/list` smoke；P0/P1 compare CLI。

未完成：真实外部 SUT adapter、严格 MCP schema 兼容层、交互式报告 UI、容器编排、真实 Trae、真实 HSM/TSA 和生产 API 接入。Null Adapter 仍是无防护基线，attack case 失败不代表任何外部 SUT 的评测结论。

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
