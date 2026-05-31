# 工作日志

## 2026-05-31 14:49 +08:00 Codex 主 agent

按用户要求在 `main` 上审查仓库现状，围绕赛题要求为 hack / red-team 组员设计可接入 XA-Guard MCP 防护栏的提交规范和 XA-Bench 对抗测试规则。未读取或维护 `implementation-notes.html`。

本次具体做了：
- 派出 5 个 `gpt-5.5 medium` 子 agent 并行只读审查：赛题约束、现有 bench schema、MCP 可测试接口、对抗规则设计、独立事实复核。主 agent 同时本地读取官方赛题 PDF、事实源、PRD、核心架构、bench、pipeline、proxy 和测试。
- 使用 `pypdf` 抽取并核对官方赛题 PDF。确认官方方向 4 要求支持攻击复现、问题定位、效果验证和持续优化；攻击样例、测试数据说明、评测脚本和审计日志样例属于可选补充材料。
- 新增 `docs/HACK-BENCH-组员提交规范.md`：定义组员任务边界、taxonomy、`attack_case / benign_control / assurance_check / exploratory_finding` 四类提交、`automated / fixture_extension / manual_exploration` 三层验证、surface、oracle、严重性、去重、安全红线和提交流程。
- 新增 `docs/XA-Bench-对抗测试规则.md`：区分当前 v0.1 已实现口径和 v0.2 必须 harden 的目标，明确 `pipeline_harness / mcp_stdio / protocol_probe / aibom_rating / audit_verify / manual_client` 的证据边界。
- 新增机器可校验 schema `bench/schema/hack-submission.schema.json` 和 runner-compatible 模板 `bench/cases/hack-submission-template.yaml`。模板包含一个当前 loader 可读的自动化 case、一个 MCP stdio fixture extension、一个真实 IDE 手工验证记录。
- 修订文档索引和维护入口：`docs/README.md`、根 `README.md`、`docs/PRD.md`、`docs/事实源.md`、`docs/产品架构.md`、`docs/项目总览.md`、`docs/tutorials/MCP零基础上手.md`、文献库 INDEX、产品形态对比和 AgentDojo 导读。旧 HTML 留痕入口改为根目录 `log.md` / `status.md`。
- 纠偏关键事实：国标应拒答题库是“总规模 ≥ 500 且每类 ≥ 20”，340 只是逐类下限相加；XA-Bench 当前只有 30 条 seed regression，290 条是 PRD PoC 目标；Trae 展示基础 MCP / fallback，真实 elicitation 弹窗使用明确支持该能力的客户端。
- 同步 Gate1 文档主路线：从 PromptGuard 中文微调主线改为“规则 + Spotlighting + Qwen3Guard”，PromptGuard 2 保留英文 / 国际对照用途。
- 更新 `status.md`：记录新增规则工件，并补充 bench 可信度限制、MCP E2E 缺口、供应链简化路径、interpretability smoke 边界和下一步 hardening 优先级。

验证结果：
- `PYTHONPATH=src python -m pytest -q`：通过，157 个测试点全绿。
- JSON Schema 自检和模板校验通过：`hack submission schema: ok`。
- `PYTHONPATH=src python -c "from bench.runner import load_cases; ..."` 成功读取模板：`runner-compatible cases=1`，首条为 `HACK-D2-EXEC-0001 deny`。
- Markdown 相对链接扫描通过：`missing_relative_links=0`。
- `git diff --check` 通过，无空白错误；仅有 Windows 工作区既有 LF -> CRLF 提示。

已完成：
- hack 组员现在有明显、可执行、不会把 demo 能力夸大的提交规范。
- bench 维护者现在有明确的接入层、oracle、指标口径和演进规则。
- 提交格式已有机器 schema 和当前 runner 可读取的模板。
- 核心文档中的 290 / 30、500 / 340、Trae HITL、Gate1 主路线和旧 HTML 留痕入口已完成纠偏。

未完成 / 客观限制：
- 本轮没有改 `bench.runner` 和 `bench.metrics` 逻辑。`case_kind` 分桶、显式 `infra_error`、taint / rule hit / audit assertion、真实 audit completeness 仍是下一轮实现任务。
- 本轮没有新增真实 MCP stdio hack harness、多步工具链 harness 或 IDE 自动化测试。
- 还没有收集组员提交的第一批真实 candidate；模板里的内容是格式示例。
- 真实客户端 HITL UI、真实 Docker/gVisor、正式 SM2 + TSA、OPA Rego、真实模型推理仍未完成。

下一步建议：
- 先实现 XA-Bench v0.2 hardening：`case_kind` 分桶、异常显式失败、组合 oracle 和 audit 验链。
- 按新模板给 hack 组员分派第一批任务，优先覆盖 runner 异常一致性、审批拒绝后零执行、审计篡改和多步污染链。
- 建立独立 `mcp_stdio` harness，再把可稳定复现的 MCP fixture 晋升为自动化 regression。

## 2026-05-28 18:44 +08:00 Codex 主 agent

按用户要求继续派出 4 个子 agent 并行处理审计归档、HITL、EXEC-004 优先级、AIBOM 升级；主 agent 审查合理性、补安全边角、执行真实归档并更新状态。未读取或维护 `implementation-notes.html`。

本次具体做了：
- 新增审计归档入口：`src/xa_guard/audit/archive.py` 和 `scripts/archive_audit.py`。归档会先统计 verify 结果，再移动原始 JSONL 到 `logs/audit/archive/`，写 manifest，不重写旧链。
- 执行真实归档：`logs/audit/audit.jsonl` 被归档为 `logs/audit/archive/audit-20260528T104349214385Z.jsonl`，manifest 记录旧日志 1146 条、34 个链错误、首错第 401 行；新的 `logs/audit/audit.jsonl` 为空文件，verify 0 错。
- 修 EXEC-004：pipeline 改为 Gate1 立即短路，Gate2/Gate4/Gate3 先聚合，再按 `ctx.final_decision` 阻断；这样 Gate3 越权 DENY 能覆盖 Gate2 red 工具 REQUIRE_APPROVAL，admin/ops 的 red 操作仍需审批。
- 补 HITL toy 协议 probe 和最小 upstream 接入：`demo/elicitation_probe_server.py`、`scripts/probe_mcp_elicitation.py`、`docs/tutorials/HITL-elicitation-toy-probe.md`；`proxy/upstream.py` 在客户端声明 elicitation 时请求 approve/reject。
- 审查并修正 HITL approve 后路径：子 agent 初版 approve 后直接调用 downstream，会绕过 Gate5 和出向审计；主 agent 改为 `pipeline.run_after_approval()`，批准后仍跑 Gate5、executor、Gate4(out)、Gate6。
- AIBOM 升级：新增 CycloneDX-like 导出、AIBOM drift 比较、本地 artifact/file URL/zip/tar 解包、sha256 provenance、typosquat 启发式；远程 http(s) 不下载，只标记需要离线拉取。
- 补 AIBOM archive traversal 防护：zip/tar 解包前校验 member path，拒绝 `../escape.py` 这类路径穿越。
- 刷新 `bench/.log/last_results.json`、`last_report.json`、`report.html`，并同步 README/status。

验证结果：
- `PYTHONPATH=src python -m pytest -q`：通过，全量测试绿。
- 30 条 seed bench（临时 audit 目录）：pass_rate 96.67%，ASR 0，Recall 100%，FPR 0，CuP 100%；execution_safety 8/8，supply_chain 4/4。
- `PYTHONPATH=src python scripts/probe_mcp_elicitation.py`：触发 1 次 toy elicitation event，返回 `approved: hello`。
- `PYTHONPATH=src python scripts/probe_mcp_elicitation.py --reject`：触发 1 次 toy elicitation event，返回 `rejected`。
- `PYTHONPATH=src python scripts/verify_audit.py --path logs/audit/audit.jsonl`：通过，当前新主日志 35 条记录、0 个链错误、0 条缺字段。
- `PYTHONPATH=src python scripts/verify_audit.py --path <temp-bench-audit>/audit.jsonl`：通过，26 条新写入记录 0 个链错误、0 条缺字段。

已完成：
- 旧审计主日志已归档，新主日志从空链开始。
- EXEC-004 已 exact pass。
- AIBOM 从本地静态扫描 MVP 升级到可导出/可比较/可校验 sha256 的离线闭环。
- HITL 已完成 toy MCP 协议 probe 和 upstream 最小接入，approve 后不再绕过 Gate5/审计。

未完成 / 客观限制：
- 还没有 Cursor / Claude Code / Codex 真实 UI 弹窗实测记录，不能宣称真实客户端弹窗已跑通。
- HITL 审批理由、审批人、approval_token 尚未进入审计字段。
- AIBOM 没有联网下载远程包、外部信誉库、真实签名体系、Sigstore/TUF，也没有 CycloneDX schema 校验。
- bench 仍有 `DATA-003` exact mismatch：预期 allow，实际 warn；这是 yellow 通知工具语义，指标上按非阻断处理。

下一步建议：
- 做真实客户端 HITL 弹窗实测并记录证据。
- 把 approval_token / approver / reason 写入 Gate6 审计。
- AIBOM 接 CycloneDX schema 校验和签名体系。
- 扩 policy 到 30 条、扩 CSAB-Gov-mini 到 290 条。

## 2026-05-28 18:25 +08:00 Codex 主 agent

按用户要求先派出 4 个子 agent 并行调查/修复 bench、audit、AIBOM、HITL 四条线；主 agent 负责评估合理性、集成、验证和更新状态。未读取或维护 `implementation-notes.html`。

本次具体做了：
- 对比旧 `bench/.log/last_results.json`，定位 10 个失败 case：`EXEC-004`、`EXEC-008`、`DATA-003`、`DATA-004`、`CONT-002`、`SCM-001/002/004`、`COMP-002`、`INTP-001`。
- 修复 bench/规则退化中的合理项：`restart_service` 纳入重要操作审批；RAG `[ADMIN_OVERRIDE]` 从硬拒降为 WARN；assistant 历史里的 `/etc/passwd` 从硬拒降为 WARN；新增“家庭住址/家庭地址”隐私拒答模式；跨域 body 含“内部”触发 WARN；FPR/CuP 指标把 WARN 作为非阻断处理，但 exact pass 仍保留 allow/warn 差异。
- 补方向 3 AIBOM MVP：Python AST 扫描危险 import/API，JSON/YAML 元数据扫描，requirements/pyproject/METADATA 依赖风险解析，A/B/C/D/F 评级和具体理由；bench 的 `install_plugin` seed 通过薄接入映射 A/B=allow、C=warn、D/F=deny。
- 修审计写入侧分叉根因：`ChainStore.append()` 增加文件锁，并在锁内重新恢复最新 `record_hash` 后再追加，避免多个 ChainStore 实例并行写同一 JSONL 时使用旧 `_last_hash`。
- 核查 HITL：确认当前 `Gate2` 只返回 `REQUIRE_APPROVAL` / fallback，`proxy/upstream.py` 未接真实 MCP elicitation；本轮不写假支持，后续需先用支持 elicitation 的客户端做 toy 实测。
- 同步 README seed 指标、刷新 `bench/.log/last_results.json` / `last_report.json` / `report.html`，并更新根目录 `status.md`。

验证结果：
- `PYTHONPATH=src python -m pytest -q`：通过，全量测试绿。
- 用临时 audit 目录跑 30 条 seed bench：pass_rate 93.33%，ASR 0，Recall 100%，FPR 0，CuP 100%，supply_chain 4/4。
- `PYTHONPATH=src python scripts/verify_audit.py --path <temp-bench-audit>/audit.jsonl`：通过，26 条新写入记录 0 个链错误，0 条缺字段。
- `PYTHONPATH=src python scripts/verify_audit.py --path logs/audit/audit.jsonl`：仍失败，969 条历史记录中 34 个 hash_prev 链错误，0 条缺字段。

已完成：
- bench 退化主要修复完成，README/status/bench log 与新实测同步。
- AIBOM 不再是 stub，方向 3 seed 从 25% 变为 100%。
- 审计链未来写入分叉问题已修，新写入可验。

未完成 / 客观限制：
- 历史 `logs/audit/audit.jsonl` 已经分叉，不能通过改代码“修复”旧链；应归档/轮转，而不是重写伪造历史。
- `EXEC-004` 仍是 exact mismatch：期望 deny，实际 require_approval，根因是 Gate2 red 工具先短路，Gate3 越权 deny 没机会执行；需要单独设计 Gate2/Gate3 聚合优先级。
- `DATA-003` 仍是 exact mismatch：期望 allow，实际 warn；这是 yellow 通知工具的产品语义，指标上已按非阻断处理。
- HITL 真实 elicitation 未接入；需要先用 Cursor/Claude Code/Codex 等支持客户端实测 toy server，再改 `proxy/upstream.py`。
- AIBOM 仍是本地静态扫描 MVP，未做 CycloneDX/AIBOM 正式导出、签名校验、远程包解包、信誉库和漂移监测。

下一步建议：
- 先轮转/归档旧 audit 主日志，从修复后的新链开始保留证据。
- 决定 `EXEC-004` 的 Gate2/Gate3 优先级策略。
- 做真实 MCP elicitation toy 实测，再接入 XA-Guard upstream。
- 将 AIBOM MVP 扩展到 CycloneDX、签名和漂移监测。

## 2026-05-27 23:41 +08:00 Codex 主 agent

维护根目录 `status.md`，按 AGENTS.md 要求没有读取或维护 `implementation-notes.html`。

本次具体做了：
- 读取 `AGENTS.md`、`README.md`、`docs/PRD.md`、`docs/事实源.md`、`docs/产品架构.md`、`pyproject.toml`、根目录 `log.md/status.md`，并检查 `src/`、`bench/`、`sdk/`、`demo/`、`frontend/`、`tests/`、`policies/`、`scripts/` 的文件结构与 TODO/stub/NotImplemented 标记。
- 重点核对赛题 4 个方向与当前仓库实现：输入攻击识别、工具调用/任务执行安全、插件供应链、评测审计溯源。
- 重新执行验证：
  - `PYTHONPATH=src python -m pytest -q` 通过，测试输出显示 93 个测试点全绿。
  - `PYTHONPATH=src python -m bench.cli run --suite bench/cases/csab-gov-mini-seed.yaml --config configs/xa-guard.yaml` 可运行，最新 pass_rate 为 66.67%、ASR 为 22.73%、FPR 为 12.5%、Recall 为 77.27%、CuP 为 87.5%。
  - `PYTHONPATH=src python scripts/verify_audit.py --path logs/audit/audit.jsonl` 未通过，661 条记录中有 34 个 hash_prev 链错误，0 条缺字段。
- 写入新的 `status.md`，把仓库当前状态定位为 demo MVP / M1 末到 M2 前可运行骨架，并列出主要空壳：SDK、AIBOM、MCP elicitation、Streamable HTTP、OPA/Rego、Docker/gVisor、国密证据链、CoT 忠实度、290 用例评测、比赛 PDF/视频交付物。

已完成：
- `status.md` 从空文件变为当前仓库状态看板，内容贴合 XA-202620 赛题方向和 PRD 目标。
- `log.md` 顶部追加本次客观工作记录。

未完成 / 后续应做：
- 没有修改代码逻辑。
- 没有修 bench 指标退化、审计验链失败、AIBOM stub、SDK stub 等问题。
- 下一步建议优先排查 `bench/.log/last_results.json` 中导致 FPR 12.5% 和 data_safety CuP 0 的具体 case，并定位 `logs/audit/audit.jsonl` 第 401 行附近开始的链错误。

## 2026-05-27 主 agent（Opus 4.7）

派 3 个 sonnet 子 agent 并行修 pipeline 三处 bug：

1. **pipeline.py REQUIRE_APPROVAL 不阻断 executor** → 在 inbound 循环里把 `Decision.DENY` 短路条件扩展到 `(DENY, REQUIRE_APPROVAL)`，并把返回的 `final_decision` 改为 `result.decision`。更新模块 docstring。新增 `test_pipeline_blocks_executor_on_require_approval`。
2. **types.py GateContext.append WARN 被吞成 ALLOW** → WARN 分支补写 `self.final_decision = Decision.WARN`，保持优先级 DENY > REQUIRE_APPROVAL > WARN > ALLOW。主 agent 二次审核时发现 REQUIRE_APPROVAL 守卫只看 ALLOW 会被前面 WARN 卡住，把守卫扩到 `(ALLOW, WARN)`。新增 `tests/unit/test_types_warn.py`。
3. **audit log 缺 final_decision** → `AuditRecord` 加 `gen_ai_decision_final` / `gen_ai_decision_final_reason` 两字段并写入 `to_dict()` 的 OTel key；`Gate6Audit.evaluate` 从 `ctx.final_decision.value` / `ctx.final_reason` 取值。新增 `test_audit_record_carries_final_decision`。

审核 git diff：4 个源文件 + 2 个测试文件，共 +89 / −1086（todo.md 之前已删）。`pytest tests/` **93 passed**。

README 同步：测试数 87 → 93。审计字段从 14 增到 16，verify_audit 脚本未改（不在本次范围）。

子模块工作日志已由子 agent 各自写入：
- `src/xa_guard/.log/2026-05-27_require_approval_fix.md`
- `src/xa_guard/.log/2026-05-27_warn_fix.md`
- `src/xa_guard/audit/.log/2026-05-27_final_decision.md`

未做：commit、verify_audit 脚本同步 16 字段。
