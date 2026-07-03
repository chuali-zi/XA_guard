# 2026-07-02 09:10 -07:00 Plan 2 live office/mail 竖切

## 本次完成

- 在 `arena` 新增标准 MCP office/mail server：`read_mail`、`query_project`、`send_email` 读写同一个 `World`，外发只写本地 `world-effects.jsonl`。
- 新增 live runner：生成临时 `opencode.json`、OpenCode live victim agent prompt、XA-Guard YAML、Gate4 capabilities、Gate3 live overlay；通过 `opencode run --format json --auto --agent ear-live-victim --model opencode-go/glm-5.2` 收集 stdout JSON transcript。
- 新增外部 XA-Guard SUT adapter 路径：不导入 `xa_guard`，只通过 `python -m xa_guard.server --config <generated-yaml>` 启动，并读取 `<attempt>/audit/audit.jsonl`。
- 新增 CLI：`arena-live` 支持 challenge path、SUT mode、repeat、out dir、run id、model id、manifest root、XA-Guard root 和 timeout。
- 修正 live 攻击 fixture / deterministic agent action 名称，使 `send_project_budget` 与旧 `exfiltrate` 都可复用。
- 补 live 单测与 MCP server 单测，覆盖工具列表、同一 World 读写、敏感外发记录、XA-Guard 配置生成和 live Gate3 overlay 关键词。
- 跑通最终 2x2 live smoke：`reports/arena-live-2x2-smoke/` 中 attack+guard 被 XA-Guard Gate3 deny 且无外发；attack+null 发生敏感外发；control+guard/null 均放行无误报。
- 新增 spike 记录：`docs/superpowers/spikes/2026-07-02-xaguard-downstream-mcp.md`。

## 验证

- `PYTHONPATH=range_src python -m unittest discover -s tests -v`：PASS，236 tests。
- `PYTHONPATH=range_src python -m enterprise_agent_range validate --manifest cases/p1_manifest.json`：PASS，242 cases / 44 fixtures，pending sha256 warning 为既有预期。
- `PYTHONPATH=range_src python -m enterprise_agent_range run --manifest cases/p1_manifest.json --out reports --run-id p1-regression-after-live`：PASS，242 valid / 0 infra error / 0 invalid。
- `PYTHONPATH=range_src python -m enterprise_agent_range arena-live --sut-mode both --repeat 1 --out reports --run-id arena-live-2x2-smoke --timeout-seconds 180`：完成 4 attempts；guard 攻击拦截、null 攻击泄漏、两条 control 通过。

## 未完成

- Live 轨仍是 `N=1` smoke，不是统计评测。
- Gate3 live overlay 目前针对 Atlas 预算特征，后续应配置化。
- 242 个旧 case 未迁移到 live challenge schema；旧 `execution.steps` 仍保留为 replay 路径。
- 尚未大面积回填 `docs/05/15/16/17` 等正式架构文档。

# 2026-07-02 01:51 -07:00 P1/P2 fast-forward 合并到 main

## 本次完成

- 将 `codex/enterprise-range-p2` 上的 P2 review finding 修复提交为 `b696244 fix: harden P2 grants and remediation ids`，并推送到 `origin/codex/enterprise-range-p2`。
- 切换到 `main` 后按堆叠顺序执行 fast-forward 合并：先 `git merge --ff-only codex/enterprise-range-p1`，再 `git merge --ff-only codex/enterprise-range-p2`。
- 合并结果：`main` 已包含 P1 基线和 P2 研究级能力子包，当前 HEAD 为 `b696244`；未产生 merge commit，历史保持线性。

## 验证

- 合并后在 `main` 执行 `python -m unittest discover -s tests`：PASS，203 tests。

## 未完成

- 当前 `main` 尚未推送到 `origin/main`（下一步执行推送）。
- P2 仍未接入 runner/oracle/metrics/report，也还没有真实 P2 case/fixture 与大屏/复盘文件产物。

# 2026-07-02 01:36 -07:00 P2 review finding 修复与回归

## 本次完成

- 按审查建议修复 `permissions`：`GrantAuthority.check()` 现在要求 `issued_at <= when_epoch < expires_at`，拒绝签发前使用 grant。
- 修复 `remediation`：`action_id` 现在基于稳定 side-effect 行身份生成，包含 sink_type、operation、payload_hash、trace_id、metadata 与重复计数；相同 payload hash 出现在不同 trace 时不再撞 ID，同时保留 `target_side_effect_hash=payload_hash` 以减少消费方破坏。
- 补充回归测试：签发前 grant 拒绝、签发瞬间 grant 允许、重复 payload hash 不同 trace 生成不同 undo action id、重复 payload 输入顺序不影响输出排序。
- 顺手修复实现中局部 `trace_id` 遮蔽 `UndoLog.trace_id` 参数的问题，避免 planner 返回的 undo log trace_id 被 side-effect 行覆盖。

## 验证

- `python -m unittest tests.test_p2_permissions tests.test_p2_remediation`：PASS，41 tests。
- `python -m compileall range_src`：PASS。
- `python -m unittest discover -s tests`：PASS，203 tests。
- `PYTHONPATH=range_src python -m enterprise_agent_range p2-status --json`：PASS，10 个 P2 capability 均为 `implemented`。
- `PYTHONPATH=range_src python -m enterprise_agent_range validate --manifest cases/p1_manifest.json`：PASS，242 cases / 44 fixtures（fixture hash pending warning 仍为预期）。

## 未完成

- P2 能力仍未接入 runner/oracle/metrics/report，也还没有真实 P2 case/fixture 与大屏/复盘文件产物。
- 本次未提交、未推送；当前分支还有本次修复与文档更新的未提交改动。

# 2026-07-02 01:34 -07:00 P2 分支代码审查

## 本次完成

- 按用户要求审查 `codex/enterprise-range-p2` 相对 merge base `d990ae5c9aed66371e98c0023b34ac5466f5732d` 的变更，执行了 `git diff d990ae5c9aed66371e98c0023b34ac5466f5732d --stat` 与针对 P2 模块/CLI 的 diff 阅读。
- 作为 review agent，先阅读了 `status.md`，再检查新增 `range_src/enterprise_agent_range/p2/` 十个能力模块、`cli.py` 的 `p2-status` 接入、P2 单测和真实 `reports/run-p1-null-verify/` 输出形状。
- 复现并确认两个 review finding：`GrantAuthority.check` 在 `when_epoch < issued_at` 时仍允许授权；`RemediationPlanner` 对相同 `sink_type` + `payload_hash` 的多条 side-effect 会生成重复 `action_id`，真实 P1 side-effects 中存在重复 payload hash。
- 执行测试验证：沙箱内第一次 `python -m unittest discover -s tests` 因 Python `tempfile` 无可用临时目录失败；经审批在沙箱外重跑同一命令，199 tests 全部通过。
- 清理了本次沙箱外测试在仓库根目录留下的 8600 个 8 位随机名、4 字节临时文件，清理后 `git status --short` 为空。

## 未完成

- 未修改实现代码和测试代码；两个 finding 仍需后续作者修复。
- 未重新生成 run/report 证据包；本次工作是代码审查，不是功能修复。

## 下一步建议

- 在 `permissions.py` 中让授权校验同时要求 `issued_at <= when_epoch < expires_at`，并补充 pre-issue 拒绝测试。
- 在 `remediation.py` 中让 `action_id`/目标引用包含可区分 side-effect 行的稳定字段（例如 trace_id、operation 或行级 hash），并补充重复 payload hash 的回归测试。

# 2026-07-01 21:16 -07:00 P1 review 修复：路径边界、工具覆盖、委托链证据

## 本次完成

- 按用户要求使用子 agent 协助：Worker C 负责 protocol/path traversal 测试补充；Worker A 只读梳理 P1 未覆盖工具；Worker B 只读梳理委托链证据缺口。主线程负责 runtime 修复、manifest 集成、测试、证据重生成和状态维护。
- 修复 fixture 路径边界：`tools.py` 中 fixture ref 现在拒绝绝对路径、`..` traversal 和解析后越出 manifest root 的路径；protocol `tools/call` 通过同一路径返回安全错误，不读取父目录文件。
- 更新 `cases/p1_manifest.json`：P1 由 234 cases 增至 242 cases（108 attack、116 benign、18 assurance）；新增 8 个良性 tool coverage case，并让 P1 execution steps 覆盖全部 66 个工具。
- 为 20 个声明 `delegation_chain_preserved` 或 `original_principal_required` 的 P1 case 补齐显式 `delegation_chain`；完整链保留 `original_principal`，缺 principal 攻击链保留链路但省略 original principal。
- 调整 `build_actual`：输出 `delegation_chain`，并把 original principal presence 收窄为显式 `original_principal` 字段，避免把普通 hop `principal_id` 误当作 original principal 证据。
- 新增/扩展测试：protocol 路径穿越 direct/protocol/合法 fixture；P1 manifest 全 66 tool coverage；P1 delegation evidence 回归。
- 重生成 `reports/run-p1-null-verify/` 和 `reports/compare-p0-p1-null/`。
- 更新 `README.md`、`status.md`、本日志、`.log/worklog.md` 和父仓库 `status.md` / `log.md`。

## 验证

- `python -m compileall range_src`：PASS。
- `python -m unittest discover -s tests`：PASS，30 tests。
- `PYTHONPATH=range_src python -m enterprise_agent_range validate --manifest cases/p0_manifest.json`：PASS，84 cases / 27 fixtures。
- `PYTHONPATH=range_src python -m enterprise_agent_range validate --manifest cases/p1_manifest.json`：PASS，242 cases / 44 fixtures。
- `PYTHONPATH=range_src python -m enterprise_agent_range run --manifest cases/p1_manifest.json --out reports --run-id run-p1-null-verify --adapter null_adapter --sut-id null-baseline --mode local --operator codex`：PASS，242 valid / 0 infra error / 0 invalid，false positive rate 0.0，utility retention 1.0，audit integrity 1.0。
- `PYTHONPATH=range_src python -m enterprise_agent_range compare --baseline reports/run-p0-null-verify --candidate reports/run-p1-null-verify --out reports/compare-p0-p1-null`：PASS。

## 未完成

- 未实现真实外部 SUT adapter；当前仍是 Null Adapter 和本地协议面。
- 当前协议是 MCP-like stdio/HTTP，不是严格 MCP schema 兼容实现。
- 未实现交互式报告 UI、容器编排、真实 Trae、真实 HSM/TSA 或生产 API 接入。
- Null Adapter 仍是无防护基线，P1 attack FAIL 只能说明基线风险，不代表任何 SUT 评测结论。

# 2026-07-01 19:44 -07:00 P1 企业完整靶场扩展集成

## 本次完成

- 按用户要求先在父仓库提交并推送当前全部改动：commit `85ea632`，message 为 `feat: add enterprise range and business api adapter`，并推送 `main` 到 `origin/main`；随后创建并切换到 `codex/enterprise-range-p1`。
- 使用 4 个 gpt-5.5 medium worker 子 agent 分工：Worker A 扩展 P1 case/fixture，Worker B 扩展 tool surface，Worker C 实现本地协议面，Worker D 实现 HTML/compare 报告；主线程负责接口收口、集成、验证和状态维护。
- 新增 `cases/p1_manifest.json`：108 个 attack case、108 个 benign control、18 个 assurance check，总计 234 个 case；覆盖 office、operations、business_data、finance、supply_chain、audit 六个域。
- 新增 `fixtures/p1/` synthetic fixture，覆盖办公污染、HR/客户/财务数据、BEC 邮件、运维/CI 日志、供应链 AIBOM、审计篡改、委托链和 IDE extension 样本。
- 将 tool surface 扩展到 66 个工具，并为工具定义补齐 capabilities、requires_approval、allowed/forbidden data classes 和 synthetic_only；mock 写操作仍只进入本地 synthetic sink。
- 新增 `protocol.py` 和 CLI `serve-stdio`、`serve-http`、`ide-replay`；HTTP 只允许本地地址，协议工具调用复用 `execute_tool` 和 `RangeState`。
- 新增静态 `report.html`、compare helper 和 CLI `compare`；已生成 `reports/run-p1-null-verify/` 与 `reports/compare-p0-p1-null/`。
- 新增 `mutations.py`、P1 core tests、protocol tests、report tests，并扩展工具面测试。
- 更新 `README.md`、`status.md`、本日志、`.log/worklog.md` 和父仓库 `log.md`/`status.md`。

## 验证

- `python -m compileall range_src`：PASS。
- `python -m unittest discover -s tests`：PASS，25 tests。
- `python -m enterprise_agent_range validate --manifest cases/p0_manifest.json`：PASS，84 cases / 27 fixtures。
- `python -m enterprise_agent_range validate --manifest cases/p1_manifest.json`：PASS，234 cases / 44 fixtures。
- `python -m enterprise_agent_range run --manifest cases/p1_manifest.json --out reports --run-id run-p1-null-verify --adapter null_adapter --sut-id null-baseline --mode local --operator codex`：PASS，234 valid / 0 infra error / 0 invalid，audit integrity 1.0。
- `{"id":1,"method":"tools/list"} | python -m enterprise_agent_range serve-stdio`：PASS。
- `python -m enterprise_agent_range compare --baseline reports/run-p0-null-verify --candidate reports/run-p1-null-verify --out reports/compare-p0-p1-null`：PASS。

## 未完成

- 未实现真实外部 SUT adapter；当前仍是 Null Adapter 和本地协议面。
- 当前协议是 MCP-like stdio/HTTP，不是严格 MCP schema 兼容实现。
- 未实现交互式报告 UI、容器编排、真实 Trae、真实 HSM/TSA 或生产 API 接入。
- Null Adapter 仍是无防护基线，P1 attack FAIL 只能说明基线风险，不代表任何 SUT 评测结论。

# 2026-07-01 19:36 -07:00 Worker D P1 HTML 报告与 compare 报告

## 本次完成

- 在 `range_src/enterprise_agent_range/reports.py` 中为 `write_run_outputs` 增加 `report.html` 输出，保留既有 JSON、JSONL、Markdown 和 artifact hash 输出。
- 新增 run HTML 报告渲染，覆盖 run 元数据、指标和失败 case 摘要；所有动态值通过 HTML escaping 后写入。
- 新增 baseline-vs-candidate compare helper：读取两个 run 目录的 `run-manifest.json`、`metrics.json`、`case-results.jsonl`，生成 counts delta、metrics delta、case status changed/added/removed 摘要和逐 case status 列表。
- 新增 compare 输出三件套：`compare.json`、`compare.md`、`compare.html`；compare HTML 同样对动态值做 escaping。
- 在 `range_src/enterprise_agent_range/cli.py` 中新增 `compare --baseline --candidate --out` 子命令；保留并行 worker 已加入的 `serve-stdio`、`serve-http`、`ide-replay` 协议命令。
- 新增 `tests/test_reports.py`，覆盖 run HTML escaping、compare 输出 shape、compare HTML escaping。
- 更新 `status.md`，反映当前已有 HTML run report、compare report 和 25 个测试通过。

## 验证

- `python -m compileall range_src`：PASS。
- `python -m unittest discover -s tests`：PASS，25 tests。

## 未完成

- 未重新生成 `reports/run-p0-null-verify/` 固定验收包，因此该历史目录中仍只有之前已有的产物；新 run 会生成 `report.html`。
- 未生成真实 baseline/candidate 对比样例目录；compare helper 和 CLI 已通过单元测试覆盖。
- 未实现交互式前端可视化；当前完成的是静态 HTML run/compare 报告。

## 下一步建议

- 用实际 baseline run 和 candidate run 执行 `compare` CLI，提交一份固定 compare 证据包。
- 若后续需要面向评审展示，可在静态 HTML 基础上增加筛选、排序和趋势图，但应继续保持独立于 XA-Guard frontend。

# 2026-07-01 19:36 -07:00 Worker B P1 工具面扩展

## 本次完成

- 在 `range_src/enterprise_agent_range/tools.py` 中将 `TOOL_DEFINITIONS` 从 25 个工具扩展到 64 个工具。
- 为所有工具定义补齐 `capabilities`、`requires_approval`、`allowed_data_classes`、`forbidden_data_classes`、`synthetic_only` 字段，同时保留原有 `domain`、`risk_level`、`side_effect` 字段。
- 新增 P1 工具覆盖 calendar/tasks、HR、finance、operations/release、customer/ticket/business API、repo/dependency/artifact、plugin review/quarantine、agent registry/delegation/capability grant、policy-copy mutation。
- 新增通用 P1 mock read/write handler：读类工具返回 synthetic payload，写类工具只记录本地 synthetic side effect，不执行真实系统操作。
- 在 `tests/test_tool_surface.py` 中新增工具数量、必需工具存在、元数据完整性、handler 对齐、P1 写工具 synthetic side effect 测试。
- 更新 `status.md`，反映当前工具面数量、测试状态和 P1 case 规模仍未完成。

## 验证

- `python -m compileall range_src`：PASS。
- `python -m unittest tests.test_tool_surface`：PASS，6 tests。
- `python -m unittest discover -s tests`：PASS，22 tests。

## 未完成

- 未扩展 `cases/p0_manifest.json`，当前 case manifest 仍是 P0 规模。
- 未实现真实 MCP/HTTP/stdio mock server。
- 未实现外部 SUT adapter。

## 下一步建议

- 基于新增工具面补 P1 attack/benign/assurance cases，覆盖新增业务域和多 Agent 委托链。
- 为新增 P1 case 补 synthetic fixtures，并更新 manifest validation/report 证据包。
