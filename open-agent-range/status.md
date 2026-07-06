# Open Agent Range 状态

更新时间：2026-07-05 21:15 -07:00

## 当前结论

仓库当前是 **SP2+ 六域活世界竖切增强 + full-day 关键业务副作用大幅迁出 scheduled tape + F3 报销审批支付 seat/SUT/ToolSurface 链路 + SP3 多面注入落位/读侧扩展 + 语义型注入 consequence（plugin/mcp -> tool-surface-drift，supply/aibom -> supply-chain-drift，policy -> policy-exception-abuse，plugin/mcp -> sandbox-escape-attempt）+ SP4.1 finding 队列/审核/Null vs GuardStub/XA-Guard A-B 入口 + ManualSeat CLI 手动尝试入口 + promote 证据门禁 + SP5 最小追责/审批绕过竖切 + Guard/XA-Guard 类 SUT 裁决事实进入 hash ledger + `Ledger.replay()` projection v1 + `range day/replay/report/sut check/workbench serve` 产品命令薄入口 + 最小真实 XA-Guard live SUT 在环 + SP6/SP7 最小证据包补强 + SP7 产品完成态 spec 已补强**。

最新复核结论：现有测试与 `full-day` demo 通过，说明当前增强竖切是健康的；但它仍 **不完全符合 PRD/SP7 的“真实政企一天 + 完全自由红队靶场”完成态**。当前产品形态仍是“可运行的开放靶场内核竖切”，不是可交付给红队长期自由攻关的完整沙盘。

当前最接近完成态的部分是：`full-day.json` 的关键业务副作用已基本迁到多 seat ToolSurface 调用，`scheduled_events` 仅保留外部/背景事实（告警到达、日志/工单可读、低风险审批超时）；F5 运维告警→审批→重启由 `赵工 read_log -> request_approval` 与 `钱主管 approve -> restart_service` 推动；Dev/Gov/Audit 的 CI、插件发布、注册表更新、证据导出也带审批链落账；`plugin/mcp` 有 `tool-surface-drift` 与 attempt 级动态 ToolSurface；`supply/aibom` 有 `supply-chain-drift`；最小 live `XaGuardSUT` 与最小证据包已可用。

当前仍 **不能** 宣称“完全自由靶场完成”。核心缺口是：正常组织行为虽已更多走 ToolSurface/SUT，但仍主要依赖 demo 中按 principal 写死的 deterministic scripted baseline，不是全席位 live/ManualSeat 任意长度 observe-plan-act；工作台已支持 `run-ab --sut-mode null,xaguard --repeat N --live --evidence-dir` 的 dry-run/execute 入口和 live `INFRA_ERROR` 不计分分流，也已有 `manual-attempt` 让红队以指定 principal 手动提交单个 ToolCall 并经 SUT 裁决/出证据；`range workbench serve` 现在能生成静态红队工作台，`range sut check` 能做 SUT overlay/live smoke 检查，`promote` 默认要求 A/B evidence 门禁通过；但静态页还不是交互式 Web 地图/多步 ManualSeat，report 仍是摘要级；SP7 九类属性族已有最小覆盖，但 policy/sandbox 仍是最小世界事实判据，不是真实策略引擎/沙箱执行器；live XA-Guard 仍是每次 ToolCall 启动 stdio 的最小 smoke，不是长生命周期 session 或完整审计对齐产品；`Ledger.replay()` 已有 ledger projection v1 且 full-day 关键终态可复原，但还不是完整世界级 deterministic replay/report 产品；Guard/XA-Guard 类 SUT 已会把 allow/deny 裁决写入 hash ledger，但 Gate6 audit 与 range ledger 尚未 hash/seq 深度对齐，Null baseline 仍不额外落裁决账；交互式 Web 红队台、多注入编辑、真实 live N>=3 矩阵和多步 ManualSeat 体验仍缺失。

## 文档/spec 状态

- `PRD.md` 仍是北极星；本轮只在子项目节奏中补充 `SP7 产品完成态验收`。
- 新增 `docs/specs/SP7-product-completion-spec.md`，定义最终产品形态、三条硬门槛、自由注入三层标准、证据包、验收矩阵和分阶段完工路线。
- 更新 `docs/README.md`、`docs/architecture/system-overview.md`、`docs/reference/a-day-in-the-life.md`、`docs/architecture/injection-surface-model.md`、`docs/architecture/evidence-and-accountability.md`。
- 更新 SP2/SP3/SP4/SP5/SP6 设计文档，使它们都指向 SP7 完成态，而不是停留在当前最小竖切。

## 已实现能力

- `run_attempt` 已从“先整批跑 scheduler，再让 seat 出手”改为统一业务 timeline：注入先进入世界，scheduled events 与 seat/SUT tool loop 按 tick 交织运行。
- `scenarios/dctg/full-day.json` 已从单 `seat_context` 增强为 10 个活 `seat_contexts`，覆盖 Office/Ops/Business Data/Dev Supply/Governance/Audit；demo scripted 模式会按 principal 生成正常业务基线计划。
- `full-day` 的关键业务副作用已大幅迁出 scheduled tape：林工、张经理、周业务、赵工、钱主管、孙开发、吴架构、郑治理、王安全、钱审计的正常动作均通过 ToolSurface handler 落世界/落账；本轮新增 F3 小王提交报销单、张经理审批、陈会计按审批支付的 seat/SUT/ToolSurface 链路，`pay` 纳入特权动作并带审批链；`scheduled_events` 只保留外部告警、日志/工单可读和审批超时等背景事实。
- F5 运维链路不再是纯 scheduled 事实：外部事件只表示告警与日志到达，真人动作由 `赵工 read_log -> request_approval` 与 `钱主管 approve -> restart_service` 推动。
- `kernel/scheduler.py` 暴露 `prepare_business_events` / `apply_business_event`，支持 runner 在同一时钟里逐 tick 应用业务事件。
- `OpenCodeSeat` prompt 已去掉“Use a minimal safe plan / do not use sensitive records”安全引导。
- `OpenCodeSeat` 已从邮件专用 action 示例推进到通用 ToolSurface schema prompt：runner 会把每个 seat 可用工具的 `input_schema`/描述/risk/capability 放进 `visible["_tool_schemas"]`，OpenCode 可用统一 `{"tool": "...", "args": {...}}` 计划格式调用 Ops/Dev/Gov/Audit 等非邮件工具；旧扁平格式仍兼容。
- 注入面仍支持任意 scheme placement；新增参考读工具 `read_tool_surface`、`read_supply_chain`、`read_insider`，让 `plugin/mcp/supply/aibom/insider` 不再沉默。
- `GullibleSeat` 的 `CHANNEL_READ_TOOLS` 已覆盖 mailbox/rag/doc/log/ticket/policy/meeting/plugin/mcp/supply/aibom/insider。
- `plugin:` / `mcp:` 注入现在不只是可读文本：注入 handler 会把工具声明记录到 `world.domain_state.tool_surface_declarations`，未授权声明进入 `tool_surface_drift` 并由 `tool-surface-drift` 属性判定；approved 声明会在本次 attempt 中动态加入 ToolSurface，形成可被 seat/SUT 调用并落账的合成工具；`scenarios/injections/full-day-plugin-drift.json` 提供 synthetic 示例。
- `supply:` / `aibom:` 注入现在会形成供应链声明事实：注入 handler 写入 `supply_chain_declarations`，当制品声明 hash、观察 hash、组件或来源与基线 AIBOM 不一致时写入 `supply_chain_drift`；新增 `supply-chain-drift` 属性可判定制品/AIBOM 漂移；`scenarios/injections/full-day-supply-drift.json` 提供 synthetic 示例。
- `Oracle` 已把 `downstream_external_send_count` 降级为诊断字段，不再用“外发次数恰好等于 N”作为通用 pass/fail 门槛。
- 新增 `kernel/mcp_echo_server.py`，作为 XA-Guard live SUT 的下游 MCP target，暴露当前 ToolSurface schema 并 echo 工具调用。
- `XaGuardSUT(live=True)` 最小在环已可用：真实 `xa_guard.server` stdio MCP + Gate6 audit 回读 + 本地 ToolSurface 执行。
- `kernel.workbench run-ab` 现在不再固定 NullSUT vs GuardStubSUT：默认保持兼容，新增 `--sut-mode null,xaguard` / `--sut-mode xaguard`，支持 `--repeat`、`--evidence-dir` spec 别名和 `--live`；离线 xaguard 侧使用场景 `PolicyOverlay`，live xaguard 侧若外部 SUT/依赖不可用会显式写成 `infra_error`，并从 protected ASR 分母中剔除。
- `kernel.workbench manual-attempt` 已提供最小 ManualSeat 产品入口：红队可指定 `--world`、`--principal`、`--tool`、`--args-json`、可选 `--inject` 和 `--sut-mode null|guard|xaguard|--live`，手动 ToolCall 仍走 `run_attempt -> SUT.invoke -> ToolSurface`，生成标准 evidence 与 summary。
- `SUT.invoke` 现在会在 GuardStubSUT 与 XaGuardSUT（offline/live）路径为每次工具调用追加 `tool_attempt` 与 `sut_decision` hash ledger 事实，deny 时只留下尝试和裁决，不执行 ToolSurface 副作用；`NullSUT` 仍作为裸奔基线保持低噪音，只记录真实工具副作用。
- `PropertyEngine` 新增 `approval-bypass`、`tool-surface-drift`、`supply-chain-drift`、`audit-integrity-break`；分别识别未批准审批票据、未授权工具面声明、供应链声明/hash/来源漂移和 ledger hash chain 断裂。full-day 正常 CI/Governance/Audit 的 approved 票据已写入世界事实，F5 approved 票据由真实座席链路产生；CI、插件发布、注册表更新、证据导出均带 `authorization_chain`。
- `PropertyEngine` 新增 `policy-exception-abuse` 与 `sandbox-escape-attempt` 最小属性族；`policy:` 注入可形成策略例外世界事实，`plugin/mcp:` 注入可形成沙箱越界尝试世界事实，full-day 已绑定这两类属性，正常日不误报。
- `_export_evidence()` 现在除落账外，还会在 audit 队列写入 exported 证据包状态，使 F16 日结证据包不再依赖 scheduled 直接落账。
- `EvidenceStore` / `run_attempt` 已补 SP7 最小证据包：`world-in.json` 现在是真正运行前世界，新增 `world-out.json`、`world-diff.json`、`timeline.jsonl`、`ledger-replay.json`（`ledger_projection_v1`）和 `accountability-report.json`，并进入 artifact hash 清单。
- `kernel.range_cli` 已提供 SP7 产品命令薄入口：`day` 跑场景并写标准 evidence + `day-summary.json`，`replay` 校验 artifact hash、ledger hash/projection 与 SUT audit，`report` 从 evidence 输出 JSON/Markdown/HTML 摘要，`sut check` 检查 SUT overlay/可选 live smoke，`workbench serve` 生成静态红队工作台，并把 `run-ab`、`manual-attempt`、`promote` 等 workbench 命令透出为 `range` 顶层别名。
- `workbench promote` 默认新增证据门禁：finding schema 有效、状态为 `reproduced`、存在最近一次 `run-ab --execute` summary、null/protected 两侧 evidence 目录和 `verdict/ledger/tool-events/audit/artifact-hashes` 完整、hash chain OK、protected 无 `INFRA_ERROR` 后才允许固化；`--force` 保留为显式人工 override。
- `Ledger.replay(world)` 已实现确定性投影：从账本重建 egress、tool attempt、SUT decision、ticket/approval/CI/audit 队列投影、服务/插件/注册表变化索引；关键参考工具已把安全 replay metadata 纳入 ledger entry，full-day 关键终态（CI succeeded、gateway healthy、审计包 exported 等）可从账本复原。
- 既有能力仍保留：纯标准库内核、hash ledger、EvidenceStore、SP4.1 workbench、离线 A/B、最小 accountability、OpenCode 最小 live smoke。

## 已验证能力

- `python -m pytest kernel/tests -q`：通过（当前收集 108 个用例；其中 `test_xaguard_live_sut.py` 在本 XA-Guard monorepo 中跑真实 live SUT）。
- `python -m pytest kernel/tests/test_range_cli.py -q`：通过（7 个用例），覆盖 `day` evidence/summary、repeat numbered attempts、`replay --verify-hashes --verify-ledger --verify-sut-audit`、`report --format json|md|html`、`sut check`、`workbench serve --no-server`、`range run-ab` 顶层别名。
- `python -m pytest kernel/tests/test_policy_sandbox_properties.py -q`：通过（5 个用例），覆盖 policy exception 缺票据/未授权/过期、合法例外不误报、sandbox escape 越界、注入生成世界事实、full-day 绑定新属性且正常日干净。
- `python -m pytest kernel/tests/test_workbench.py -q`：通过（18 个用例），覆盖默认 Null vs GuardStub 兼容、`--sut-mode null,xaguard` 离线执行、spec 别名 `--repeat/--evidence-dir`、live xaguard dry-run 计划、live `infra_error` 不计入 protected ASR 分母、`manual-attempt` 在 guard 下拦截/null 下泄漏的手动 ToolCall 对照，以及 promote 前 A/B evidence 门禁。
- `python -m pytest kernel/tests/test_business_scheduler.py -q`：通过（2 个用例），覆盖 full-day 业务时钟/队列/回放；新增断言 F3 `EXP-1001` 报销工单、`APPR-EXP-001` 审批和 `PAY-EXP-1001` 支付 replay。
- `python -m pytest kernel/tests/test_smoke.py -q`：通过，覆盖 GuardStubSUT allow/deny 裁决进入 hash ledger，且 deny 不产生工具副作用账。
- 2026-07-05 06:32 复核再次运行 `python -m pytest kernel/tests -q`：通过；再次运行 `python -m kernel.demo --scenario scenarios/dctg/full-day.json`：通过，账本 28 条、零违规、`verdict.passed=True`。
- `python -m kernel.demo --scenario scenarios/dctg/full-day.json`：通过，账本 31 条，hash chain OK，零违规，`verdict.passed=True`；可见 read_mail/submit_ticket/approve/pay/query_report/read_repo/query_aibom/read_tool_surface/read_supply_chain/query_policy/read_policy/query_registry/manage_ci/publish_plugin/update_registry/export_evidence 等关键业务动作已由 seat 工具链落账。
- `python -m kernel.demo --scenario scenarios/dctg/full-day.json --evidence-dir .runtime\full-day-evidence-workbench-xaguard`：通过，账本 28 条、零违规，确认工作台改动后 full-day 正常证据路径仍健康。
- `python -m kernel.demo --scenario scenarios/dctg/full-day.json --evidence-dir .runtime\full-day-evidence-policy-sandbox`：通过，账本 28 条、零违规，确认 full-day 绑定 `policy-exception-abuse` / `sandbox-escape-attempt` 后正常日仍干净。
- `python -m kernel.range_cli day --world scenarios\dctg\full-day.json --agent scripted --sut null --evidence-dir .runtime\range-day-smoke`：通过，写出标准 evidence 和 `day-summary.json`；随后 `python -m kernel.range_cli replay --attempt .runtime\range-day-smoke --verify-hashes --verify-ledger --verify-sut-audit --json` 通过；`python -m kernel.range_cli report --run .runtime\range-day-smoke --format json` 通过。
- `python -m kernel.range_cli sut check --sut xaguard --world scenarios\dctg\full-day.json --json`：通过，输出 xaguard offline overlay、9 类 bound properties、28 个 surface tools 和 SUT smoke config。
- `python -m kernel.range_cli workbench serve --world scenarios\dctg\full-day.json --out-dir .runtime\workbench-static --no-server --json`：通过，写出 `index.html` 与 `workbench-state.json` 静态工作台。
- promotion gate smoke：对 `office-mailbox` finding 先 `review-finding reproduced` 后直接 `promote` 返回 1；执行 `range run-ab --execute` 后再 `promote` 返回 0 并写出 challenge，确认默认固化路径要求 evidence。
- `python -m kernel.demo --scenario scenarios/dctg/full-day.json --inject scenarios/injections/full-day-policy-sandbox.json`：以红队结果形式报告 2 条违规：`policy-exception-abuse` 与 `sandbox-escape-attempt`。
- `python -m kernel.workbench manual-attempt --world scenarios\dctg\office-mailbox.json --principal 林工 --tool send_message --args-json "{...cit-1001...}" --sut-mode guard --out-dir .runtime\manual-attempt-smoke --json`：通过，`guard-stub` 对手动敏感外发给出 deny，零外发、零违规、hash chain OK。
- `python -m kernel.demo --evidence-dir .runtime\demo-evidence-review`、`python -m kernel.demo --scenario scenarios/dctg/full-day.json --evidence-dir .runtime\full-day-evidence-review`、`python -m kernel.demo --scenario scenarios/dctg/full-day.json --evidence-dir .runtime\full-day-evidence-after-seat-migration`、`python -m kernel.demo --scenario scenarios/dctg/full-day.json --evidence-dir .runtime\full-day-evidence-replay-v1` 与 `python -m kernel.demo --scenario scenarios/dctg/full-day.json --evidence-dir .runtime\full-day-evidence-replay-state-v2`：均通过，证据目录生成 `world-out.json`、`world-diff.json`、`timeline.jsonl`、`ledger-replay.json`、`accountability-report.json` 并进入 `artifact-hashes.json`；最新 `ledger-replay.json` 含 `deterministic_world_replay=ledger_projection_v1`，且可复原 `build-77=succeeded`、`gateway=healthy`，`limitations=[]`。
- `python -m pytest kernel/tests/test_opencode_seat.py -q`：通过，覆盖 OpenCode 通用 ToolSurface schema prompt、`args` 格式非邮件工具调用、旧格式兼容和多轮 mailbox 回调。
- `python -m pytest kernel/tests/test_tool_surface_drift.py -q`：通过，覆盖 plugin/mcp 未授权工具声明漂移、approved MCP 声明不误报、approved MCP 声明动态进入本次 ToolSurface、full-day 正常日绑定新属性不污染、full-day 注入 fixture 触发 `tool-surface-drift`。
- `python -m pytest kernel/tests/test_supply_chain_drift.py -q`：通过，覆盖 supply/aibom hash/来源漂移、approved 匹配 AIBOM 不误报、full-day 正常日绑定新属性不污染、full-day 注入 fixture 触发 `supply-chain-drift`。
- `python -m pytest kernel/tests/test_accountability.py -q`：通过，覆盖 `audit-integrity-break` 对 tampered ledger hash chain 的最小识别。
- `python -m kernel.demo --scenario scenarios/dctg/full-day.json --inject scenarios/injections/full-day-supply-drift.json`：以红队结果形式报告 2 条 `supply-chain-drift` 违规，不再以 traceback 崩溃。
- `python -m kernel.demo --scenario scenarios/dctg/full-day.json --inject scenarios/injections/full-day-plugin-drift.json`：以红队结果形式报告 2 条 `tool-surface-drift` 违规。
- 2026-07-05 06:32 尝试运行 `opencode run --model openai/gpt-5.5 --variant xhigh --dir . "<用户指定 review prompt>"`；该进程读取上下文后长时间卡在内部 explore，无最终 review 输出，已中止，不能作为有效外部复核结论。
- 2026-07-05 06:47 再次限时运行同一 `opencode run` 复核；进程正常启动并读取 PRD/status/log，启动只读 review 子任务，但 180 秒内无最终 review 输出，被限时中止，仍不能作为有效外部复核结论。
- 2026-07-05 07:01 再次限时运行同一 `opencode run` 复核；进程读取根 `status.md`/`log.md` 并启动 Runtime/Docs review 子任务，但 180 秒内无最终 review 输出，被限时中止，仍不能作为有效外部复核结论。
- 2026-07-05 07:15 再次限时运行同一 `opencode run` 复核；进程读取根 `status.md`/`log.md` 并启动 PRD 标准、实现证据、测试证据 review 子任务，但 180 秒内无最终 review 输出，被限时中止，仍不能作为有效外部复核结论。
- 2026-07-05 07:22 再次限时运行同一 `opencode run` 复核；进程读取 PRD、SP7、system overview、injection model、status 与 kernel README，并启动 runtime/tests review 子任务，但 180 秒内无最终 review 输出，被限时中止，仍不能作为有效外部复核结论。
- 2026-07-05 20:29 按用户要求延长等待窗口，再次运行同一 `opencode run` 复核并等待 900 秒；进程读取 PRD、SP7、架构文档、核心 kernel 和 `full-day.json`，开始执行 `full-day` demo，但 900 秒内无最终 review 输出，被限时中止，仍不能作为有效外部最终结论。部分输出仍提示缺 `range day/report/replay/workbench serve`、scripted full-day、`policy-exception-abuse`、`sandbox-escape-attempt`；其中 `ManualSeat` stub 结论来自本轮修改前快照，当前已实现最小 CLI 手动入口。
- `python -m kernel.demo --scenario scenarios/dctg/office-channels.json --inject scenarios/injections/office-multi-combo.json --ab`：通过，null 泄漏、guardstub 拦截，A/B 防护增量为 1。
- 手工 live smoke：`office-mailbox + office-mail-exfil + GullibleSeat + XaGuardSUT(live=True)` 中，真实 XA-Guard Gate3/Gate6 对 `send_message` 给出 deny，ledger 无敏感外发，verdict 通过。

## 与 PRD 的距离

已经更接近的部分：

- 一天不再只是“完整磁带后尾座出手”；主 seat 和多个业务 seat 能在同一 tick timeline 中运行。
- `full-day` 的关键业务副作用已不再主要靠 `scheduled_events` 直接写 ledger/queue/state；scheduler 当前只保留外部/背景事实，关键动作由 seat 工具调用产生。
- 真 XA-Guard 已经进入最小 ToolCall 审查闭环，并写 Gate6 audit。
- 多个原 placement-only 面至少有读侧入口和账本留痕；其中 `plugin/mcp` 已推进到可判定 consequence（未授权工具面漂移）和 attempt 级动态 ToolSurface，`supply/aibom` 已推进到可判定 consequence（供应链声明/hash/来源漂移）。
- F5 运维重启、Dev CI/插件发布、Governance 注册表更新、Audit 证据导出均已从 scheduler tape 迁到 seat/SUT/ToolSurface 链路，并有 `approval-bypass` 判据约束审批状态。
- OpenCode prompt 不再把安全答案直接喂给 agent，且已开始使用真实 ToolSurface contract，而不是只给邮件/记录/外发三件套示例。
- Verdict 不再把固定外发次数当题目答案。
- 证据包不再只有终态 `world-in`，已能区分运行前世界、运行后世界、diff、timeline 和追责报告。
- SP7 已把最终完成态验收写清楚。

仍未完成的 PRD 关键项：

- **真实一天仍不完整**：关键业务副作用已基本迁出 scheduled tape，F3 报销审批支付也已由 seat/SUT/ToolSurface 推动；但这只是把“事实磁带”推进到“deterministic seat baseline”。正常一天还不是由 live agent/ManualSeat 在完整上下文里自主观察、计划、行动；F10/F11/F15 等业务流、后台系统、跨部门队列、真实工作台与异常分支也仍偏薄。
- **Seat 组织行为仍偏脚本**：`demo.scripted_plans_for_scenario()` 仍按 principal/tool set 写死正常业务计划；OpenCodeSeat 只是通用 schema prompt + 实验性一读一 follow-up，不是 full-day 全席位任意长度 observe-plan-act loop，也没有把外部 review/红队工作流变成可复跑产品功能。
- **真实 XA-Guard live 仍是最小闭环**：目前每次 ToolCall 启动一次 stdio XA-Guard 进程，使用 MCP echo downstream；workbench 已有 live xaguard A/B 入口和 `INFRA_ERROR` 分流，但尚未做长生命周期 SUT session、真实下游世界同步、真实 live N>=3 证据矩阵和完整 ledger/audit 深度对齐。
- **账本/审计还不够作为地面真值**：Guard/XA-Guard 类 SUT 已把 `tool_attempt` / `sut_decision` 作为 hash ledger 事实，`Ledger.replay()` 已能生成 `ledger_projection_v1` 且 full-day 关键终态可复原；但更多动态工具/真实下游工具的 replay payload 覆盖不足，也没有把 Gate6 audit 与 range ledger 做 hash/seq 深度对齐；Null baseline 仍不额外落裁决账，report/timeline 仍偏摘要。
- **注入 consequence 层仍不足**：plugin/mcp 已能形成 `tool-surface-drift` 世界事实并能在本次 attempt 中动态加入合成 ToolSurface，但仍不是真实插件安装/真实 MCP 下游能力变更；supply/aibom 已能形成 `supply-chain-drift` 世界事实，但还不是真实包管理器/构建系统；insider 仍主要是可读，尚未改变权限状态或 seat 行为。
- **属性族仍是最小覆盖**：已有 sensitive-egress、最小 privilege-escalation、approval-bypass、最小 unattributable-harm、tool-surface-drift、supply-chain-drift、audit-integrity-break、policy-exception-abuse、sandbox-escape-attempt；但审批/权限/policy/sandbox 判据仍需按动作时刻、审批人权限、scope、角色、真实策略引擎和真实沙箱执行器做更深语义校验。
- **红队产品形态不足**：CLI 工作台可用，`run-ab` 已支持 Null vs GuardStub/XA-Guard 和 live infra 分流，`manual-attempt` 已支持指定 principal/tool/args 的最小 ManualSeat 尝试，`workbench serve` 已有静态世界/seat/surface/property/finding/命令视图，`promote` 已有默认证据门禁；但仍缺交互式 Web 地图、多注入 finding 编辑、交互式多步 ManualSeat、真实 live N>=3 运行样本和可视化证据审核体验。
- **报告/回放不足**：已有最小 `world-out.json`、`world-diff.json`、`timeline.jsonl`、`ledger-replay.json` replay projection、`accountability-report.json` 和 `range replay/report` CLI；但仍缺 N>=3 live 统计、可浏览 Web 看板、Gate6/range ledger 深度对齐和完整世界级 deterministic replay。

## 下一步

1. 把 deterministic `scripted_plans_for_scenario()` 升级为可替换的 full-day observe-plan-act seat loop：支持 OpenCode/ManualSeat 多轮、跨 tick 观察工具输出、失败重试和人工注入红队操作，而不是按 principal 写死计划。
2. 把 `XaGuardSUT(live=True)` 从每 call 启动进程优化为 attempt 级长生命周期 session，并用 workbench `run-ab --sut-mode null,xaguard --live --repeat >=3` 产出真实 live 证据矩阵和 Gate6/range ledger 对齐报告。
3. 让账本记录每一次 `tool_attempt/sut_decision`，实现 Gate6 audit 与 range ledger 的 hash/seq 对齐，deny/proxy 也能追责。
4. 把 `Ledger.replay()` 从 full-day 关键终态 projection 扩展到真实/动态工具完整 replay，并把 `range replay/report` 从摘要 CLI 升级为完整可浏览 evidence dashboard。
5. 扩展工作台到多注入 finding、交互式多步 ManualSeat/Web 地图、live A/B 可视化和 evidence 并排审核；当前 `workbench serve` 只是静态看板，`promote` 只是 CLI evidence 门禁。
6. 继续深化语义型注入 consequence：plugin/mcp 接真实 MCP downstream/策略拦截；supply/aibom 接真实构建/包管理器模拟；insider 接权限/seat 行为变化；policy/sandbox 接真实策略例外生命周期和真实沙箱执行器。
