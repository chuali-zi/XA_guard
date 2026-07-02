# 仓库状态：XA-Guard / XA-202620

> 快照日期：2026-07-01 05:42 PDT（仓库环境；docs 已完成物理重构；Agent Governance v1、业务 API 静态接入、项目级 OpenCode gpt-5.5 xhigh 配置与独立 Enterprise Agent Range 靶场设计文档已在当前工作树）
> 本文件仅描述当前仓库状态、验收边界与剩余差距，不记录工作历史。
> 2026-06-20 已在 commit `432ebbc` 实跑 L3 静态验收 S1–S7（全 PASS，123 测试）与能力范围内真实验收 R2/R3/R4/R6/R7/R9；证据目录 `D:/evidence/l3-20260620T090452Z/`（final-report.json + artifact-hashes.json 149 文件）。R6 Docker build/up+healthz 已 PASS（gVisor runsc 仍 BLOCKED，Windows 无 runsc）。BUG-R9 已修复+回归测试。仍 BLOCKED：R1 独立双 500/holdout、R5 真实 Trae GUI、R6 gVisor runsc（需 Linux）、R8 外部 AIBOM 生成器、R9 第三方 TSA/HSM；R2/R3 比赛目标现按 OpenCode Go 订阅 `$60` 预算型抽样管理。
> 2026-06-21 对 commit `6cf1ce9` 复核：统一静态 verifier `11/11` sections PASS；全量 pytest 在默认 Windows/CP1252 子进程环境为 `561 passed, 1 failed, 1 skipped`，总覆盖率 `79%`。唯一失败是 `validate_csab_gov_mini.py` 输出 Unicode 箭头触发 `UnicodeEncodeError`，设置 `PYTHONUTF8=1` 后该用例通过；唯一 skip 是本机缺 `xa-guard/sandbox:latest` 测试镜像。故当前不能写”默认环境全量测试全绿”。
> 2026-06-22 用户授权的 `$10` 首批运行已安全停止，证据 `D:/evidence/r2-r3-budget10-20260622/`。实际新增 provider 成本 `$2.94602940`（calibration `$1.95051700` + retry `$0.99551240`），87 次调用全部 settled、无未知成本；32 calibration jobs 为 7 complete / 25 infra_error，其中 24 个在桶余额不足时调用前阻断、1 个为 OpenCode content schema 波动。校准不完整，`budget-freeze` 正确拒绝，未生成正式 sample manifest 或 sampled 指标；旧 7 个结果不得混入正式分母。当前新正式口径为 `subscription_budget60_v1`：总 cap `$60`，calibration `$6`、R2 `$32`、R3 `$16`、retry `$6`。离线 runner 已修复 content block、R2/R3 turn retry、retry 分桶、预算停止、provider 配额暂停、结果 provenance，以及按全局未完成列表续考；AgentDojo 同一 job 恢复时不再强制重跑已完成内部 task。单题连续基础设施失败默认最多 2 次，之后不再阻塞后续题。尚未做新的付费校准。2,986-job 全矩阵仍为 `DEFERRED_OPTIONAL`。
> 2026-06-22 当前工作树离线验证：R2/R3 目标测试 `32 passed`，changed-file ruff PASS；设置 `PYTHONUTF8=1` 的全仓测试共 585 项，结果 `584 passed, 1 skipped`，唯一 skip 为本机缺 `xa-guard/sandbox:latest`；统一静态 verifier `11/11` sections PASS。未执行任何模型调用。
> 2026-06-23 新增 `docs/research/force-ai-security-2026/`，将用户提供的 FORCE 原动力大会企业 AI / 智能体安全 PPT 照片整理为专题资料：逐页笔记、风险图谱、治理架构、数据/控制流安全、XA-Guard 映射和行动清单。该资料属于研究与答辩素材沉淀，不改变当前代码验收状态，也不构成任何新增测试或正式验收通过声明。
> 2026-06-30 新增 `docs/workplan/TODO.md` 作为当前下一步执行入口，并更新 `docs/README.md` 导航。该整理明确官方 D1-D4、赛题四方向证据、L3 BLOCKED 项、R2/R3 sampled 口径和 docs 后续整理计划；不改变代码能力、测试结果或 L3 验收状态。
> 2026-06-30 Agent Governance v1 已从 `codex/agent-governance-platform` 合入当前 main 工作树：新增本地治理 registry、Gate1 前治理预检、MCP `_xa_guard` envelope 提取与剥离、`gen_ai.governance.*` 审计字段、pending ledger 透传、Gate3 治理变量和静态治理控制台；已包含 review 修复（空 allow-list 默认 fail-closed、跨主体 `all` 不自动放行、Capability Token 只落摘要、前端治理控制台 HTML escape、默认 tenant 回写）。该能力默认关闭，不改变既有 L3 验收口径。
> 2026-06-30 合并后验证：治理单测/集成/配置 20 passed；pipeline/Gate3/Gate6/pending/MCP e2e 回归通过；R2/R3 预算关键测试 32 passed；ruff 针对变更 Python 文件通过；`node --check frontend/governance.js` 通过；治理样例 JSON/NDJSON 解析通过；设置 `PYTHONPATH=src;.` 与 `PYTHONUTF8=1` 后全仓 `pytest -q` 通过，唯一 skip 仍为本机缺 `xa-guard/sandbox:latest` 镜像。
> 2026-06-30 docs 已完成物理重构：`docs/` 顶层只保留 `README.md`，原顶层文档迁入 `source-of-truth/`、`planning/`、`workplan/`、`delivery/`、`acceptance/`、`gates/`、`bench-redteam/`、`research/`；新增 `docs/workplan/NEXT-WORK-DESIGN.md`、D1 草稿、D3 视频脚本和提交清单骨架。该整理不改变代码能力、测试结果、L3 验收或比赛达标结论。
> 2026-07-01 新增全链路额外压力测试 `tests/integration/test_full_gate_stress_extra.py`：覆盖企业治理预检与 Gate1-Gate6 的 allow/deny/require_approval/warn、审批恢复、审批篡改、出向拦截、executor 异常和审计链。为保持既有静态 verifier 路径契约，补充 docs 顶层兼容入口指向重构后的真实文档；这不改变 L3 真实验收 blocker。
> 2026-07-01 修复 Gate4 出向 `output_taint` 未回写 `ctx.taint` 导致 Gate6 审计敏感级别可能保留入向标签的问题；新增真实下游业务 HTTP API stdio adapter、仓库内 `.env.example`、业务 API 配置、Gate3/Gate4 策略登记、企业 registry 授权路径和验收文档。新增业务 API 单测/集成 11 passed；ruff 通过。
> 2026-07-01 用户确认后启动 Docker Desktop 并构建本机 `xa-guard/sandbox:latest`；`tests/integration/test_sandbox_runner.py` 从 skip 变为真实执行通过，验证禁网和只读 rootfs；全仓 `PYTHONPATH=src;.` 下 `pytest -q` 通过，当前无 skip 摘要。
> 2026-07-01 新增项目级 `.opencode/opencode.json`，将本仓默认 OpenCode 模型与内置 build/plan/general/explore agent 配置为 `openai/gpt-5.5`，并设置 `options.reasoningEffort: xhigh`；该配置仅影响重启后的 OpenCode 会话，不改变 XA-Guard 产品能力或验收结论。
> 2026-07-01 新增 `enterprise-agent-range/` 独立企业级智能体安全靶场设计区，包含自有 `docs/`、`status.md` 和 `.log/worklog.md`；设计覆盖重型企业场景、解耦契约、架构、数据模型、数据流、攻击分类、场景矩阵、评测指标和证据规范。该目录明确只把 XA-Guard 作为外部 `SUT`，不导入 `src/xa_guard`、不复用既有 `docs/`，当前仅为文档设计，不改变 XA-Guard 运行时能力或 L3 验收状态。

## 总体结论

仓库已达到 **L3 静态实现验收通过 + L3 核心工程原型可运行 + 部分真实环境验收通过**：
- 静态 S1–S7 全部 PASS（双 500 implementation、Gate1 holdout 协议、AgentDojo/InjecAgent runner、性能入口、Trae/gVisor/OPA 静态、AIBOM/国密/审计/faithfulness 单测；S7 含 BUG-R9 回归测试 123 passed）。
- 真实验收已通过：R4 性能（进程内 500 + HTTP 10 会话/500，四项 PRD 中等档全达标）、R6 Docker build/up + healthz（6/6 steps PASS，容器 live healthy）、R7 OPA parity（真实 OPA 1.17.0 与 Python fallback 7/7 一致 + strict_opa fail-closed 确认）、R2 install_plugin + AgentDojo baseline + InjecAgent base/defended 真实 opencode smoke（官方上游 pinned，official_claim=False）、R9 本地 SM2-with-SM3 签验 + 篡改检出 + faithfulness 独立重算 + 本地 TSA anchor（含 SM2-TSA-token 路径，BUG-R9 修复后 PASS）。
- 20 会话容量如实记录为 LIMIT（P95 366.979ms > 300ms），未声明支持。
- BUG-R9（SM2-TSA-token anchor 验证 mismatch）已修复：`tsa.py` `_payload_for_hash` 排除 `sm2_tsa_*` 字段，新增回归测试，S7 全套 123 passed 无回归。
- BUG-R9 修复及回归测试已进入 commit `6cf1ce9`，本快照随之同步。2026-06-21 全量测试默认 Windows 编码下还有 1 个可复现兼容性失败。
- 当前 main 工作树的 Agent Governance v1 进一步补齐“员工、Agent、数据域、预算/产出归属”的企业控制面；当前治理预检为 fail-closed 语义，Capability Token 仅落摘要，静态控制台已做基础 HTML 转义。该能力默认关闭，不改变既有 L3 验收口径，也不构成 SaaS 或完整 Shadow AI / 多 Agent 编排治理实现声明。

当前仍**不能宣称“L3 最终验收通过”或“赛题最终达标”**。剩余比赛差距：R1 正式双 500/holdout 独立评测、R2/R3 `subscription_budget60_v1` 真实校准与 sampled 结果、R5 真实 Trae GUI、R6 真实 Linux/gVisor runsc 隔离、R8 外部 AIBOM 生成器、R9 第三方 TSA/HSM，以及 D1/D3/D4 交付物。2,986-job 全矩阵不在比赛差距内。

按 PRD 的 D2 代码交付清单看，README、Compose、79% 覆盖率、六关测试、32 条 Gate3 baseline 规则、审计实现和 Apache-2.0 LICENSE 已具备；公开 remote 已配置，但真实 Trae 验收仍缺。按项目自定义的 `docs/acceptance/L3-test-and-acceptance.md`，R1/R2/R3/R5/R6/R8/R9 仍有必验项 BLOCKED，因此 L3 整体仍为 **BLOCKED，而非 PASS**；其中 R2/R3 blocker 是预算型抽样工具/结果未完成，不是可选全矩阵未跑。仓库内也未发现 D1 技术方案成稿、D3 演示视频或 D4 报名材料；这不影响代码静态 L3，但影响赛题完整交付。

2026-06-23 新增的原动力大会 AI 安全专题资料进一步强化了“Agent Gateway、Agent 身份治理、控制流/数据流隔离、AI Resilience、多 Agent 编排治理”的产品叙事，但目前只是文档沉淀，尚未转化为新的实现、测试或验收证据。

2026-07-01 新增的 `enterprise-agent-range/` 是独立靶场设计工作区，用于后续红队、漏洞和能力检测规划；它不属于 XA-Guard 主产品源码，不进入现有 L3 通过项，也尚未产出可执行评测结果。

2026-06-30 后，`docs/README.md` 是文档唯一入口，`docs/workplan/NEXT-WORK-DESIGN.md` 是下一步工作设计入口，`docs/workplan/TODO.md` 是详细 TODO；`status.md` 仍只描述当前仓库状态和验收边界，工作历史继续写入 `log.md`。

## 当前实现快照

| 验收面 | 当前状态 | 边界 |
|---|---|---|
| L3 static-only (S1–S7) | 2026-06-20 实跑全 PASS：S1 双 500 implementation + formal 负测、S2 holdout 协议 8 测、S3 runner 9 测、S4 性能入口 7 测、S5 Trae 3/3、S6 compose+gVisor/OPA/deployment+17 测+OPA bundle、S7 修复后 123 测 | 静态 PASS 不等于最终验收 PASS；BUG-R9 修复现已进入 `6cf1ce9` |
| 当前全仓测试/覆盖率 | 2026-07-01：新增全链路压力测试 23 passed；新增业务 API adapter 单测/集成 11 passed；Gate/治理/审计/配置/策略资产回归通过；已构建本机 `xa-guard/sandbox:latest`，sandbox runner 真实执行通过；`PYTHONPATH=src;.` 下全仓 `pytest -q` PASS，当前无 skip 摘要；ruff PASS。最近记录覆盖率仍为 79% | 本轮未重新生成 coverage；真实业务 API 使用本地 fake server 验证，尚未接生产 endpoint；Docker 镜像存在于本机 Docker Desktop 存储，不属于仓库内容 |
| Agent Governance v1 | 已合入 main 工作树：本地 registry、运行时 preflight、MCP `_xa_guard` envelope、审计扩展字段、`frontend/governance.html` 控制台和工资条越权/HR 审批样例；包含 fail-closed allow-list、跨主体访问限制、token 摘要审计、前端 HTML 转义和默认 tenant 一致性修复；合并后目标测试与相关回归通过 | 默认关闭；v1 是私有化演示控制面，不是 SaaS；成本为估算归属，不是供应商账单；尚未接真实企业 SSO/IAM、真实 Trae GUI 或多 Agent 编排治理 |
| 真实业务 API adapter | 新增 `demo.targets.business_api_target` stdio MCP adapter，固定暴露 `business_get_status`、`business_query_record`、`business_submit_ticket`；仓库内 `.env.example`、`.gitignore` 忽略真实 `.env`、`configs/xa-guard.business-api.yaml`、Gate3/Gate4 策略和企业 registry 授权路径已具备；API key 不进入工具参数、pending ledger 或 Gate6 audit | 本轮只用本地 fake HTTP server 做成功/401/429/5xx/timeout/非 JSON/脱敏和 pipeline 集成验证；不写系统环境变量，不写用户目录配置，不代表真实业务 API 已上线 |
| 双 500 语料 (R1) | implementation profile 500+500、1000 唯一 payload、17 类各≥29 已实测验过；formal 正确非零退出 | formal 所需独立 attestation/taxonomy/semantic-group 复核 BLOCKED，不能作为正式双 500 |
| Decision faithfulness (R9c) | 本轮 25 条真实签名审计独立重算 100% 一致；直接函数验证非固定 1.0（不一致 deny→0.45） | 真实 agent trace 的大规模独立重放未完成 |
| LangChain / LangGraph | wrapper、callback/observer、HITL resume、node/tool 等适配已实现 | 固定真实版本及真实 agent/transport 端到端验收未完成 |
| Trae (R5) | 配置模板、接入文档和 allow/deny/taint/pending 四案例静态资产 S5 PASS | 真实 Trae GUI 工具发现/调用/HITL/日志/截图 BLOCKED（按用户指示跳过 GUI） |
| gVisor (R6) | 静态 runsc/禁网/只读根/非 root/cap_drop/no-new-priv/资源限制 S6 验过；**Docker build/up + healthz 真实 PASS（6/6 steps，容器 live healthy，镜像 xa-guard:latest+sandbox:latest 构建成功）** | 真实 Linux/runsc 隔离 BLOCKED：Windows Docker Desktop 无 runsc runtime（runtimes=[runc,containerd,nvidia]），需 Linux 主机 |
| OPA (R7) | 本轮真实 OPA 1.17.0 与 Python fallback 7/7 parity；strict_opa fail-closed 在 gate3_policy.py:59-60 确认 | 真实 OPA 固定镜像 provenance/license、漂移负测与完整 fixture 矩阵未跑 |
| AIBOM (R2/R8) | 内部扫描/评级/签名/漂移/离线 preflight S7 测过；真实 opencode install_plugin smoke PASS（AIBOM F deny） | 合法外部生成器真实产物/marketplace/IDE 安装链 BLOCKED |
| 审计与国密 (R9) | 本轮真实 SM2-with-SM3 签验 25 条 0 错误 + 篡改检出；本地 TSA anchor（**含 SM2-TSA-token 路径，BUG-R9 修复后 PASS**）验过；faithfulness 重算 PASS | 第三方 TSA/HSM BLOCKED（本地 file TSA + 软件 SM2 key 仅为 demo/CI） |
| 外部 benchmark (R2/R3) | 完整矩阵 CLI 保持兼容；`subscription_budget60_v1` 已实现确定性 manifest、四桶 ledger、调用前熔断、全局未完成题续考、完成题跳过、AgentDojo 内部 task cache 复用、R2/R3 turn retry 的 retry 分桶、provider 配额暂停、跨 resume 失败上限、运行前 commit/clean/权限 hash 复核及 sampled Wilson 聚合；profile/claim scope 也与冻结配置一致。默认每批 8 jobs、单题最多 2 次基础设施尝试。目标回归 32 项与 ruff 已通过。2026-06-22 历史 `$10` 运行仍只有 7/32 calibration jobs complete，不进入新正式指标 | 新 `$60` 正式校准和 sampled 结果仍 NOT RUN。AgentDojo suite/arm 批量运行和官方 utility trace 批量复用仍未实现；OpenCode 内部工具禁用仍依赖 `--pure`、隔离目录及已冻结权限配置，尚无经真实 CLI 验证的更细粒度硬开关；`$0.20` 是调用前保守预留，不是 provider 单次响应的可证明上限。旧结果不得写入正式分母 |
| 性能 (R4) | 本轮实测：进程内 500 P50 2.912ms/P95 21.72ms/QPS 415.17/RSS 62.59MB；HTTP 10×500 P95 169.79ms/QPS 74.09/RSS 103.76MB、500/500 审计 marker 匹配，全达标 | 20 会话容量 LIMIT（P95 366.979ms > 300ms，未声明支持）；多 worker/TLS/多机 soak 未跑 |
| 研究与答辩资料 | `docs/research/force-ai-security-2026/` 已整理 FORCE 原动力大会企业 AI / 智能体安全现场照片，形成逐页笔记、风险图谱、治理架构、数据/控制流安全、XA-Guard 映射和落地清单；可用于后续 D1 技术方案、答辩 PPT 和产品叙事补强 | 来源为现场照片和用户口述印象，未做外部事实核验；其中外部事件、金额、法律案例、厂商能力不得直接作为正式引用；尚未转化为代码实现或验收证据 |
| 文档执行入口 | `docs/README.md` 已成为唯一文档入口；`docs/workplan/NEXT-WORK-DESIGN.md` 汇总下一步工作设计；`docs/workplan/TODO.md` 保留详细 TODO；`docs/delivery/` 已有 D1 草稿、D3 视频脚本和提交清单骨架 | 本次仅重构文档结构、修链接和补工作设计，不新增代码能力、测试结果、付费评测或正式提交材料 |
| OpenCode 项目配置 | 仓库内新增 `.opencode/opencode.json`，项目默认模型为 `openai/gpt-5.5`，内置 build/plan/general/explore agent 均设置 `options.reasoningEffort: xhigh` | 配置需重启 OpenCode 后生效；未改全局用户配置，不改变 XA-Guard 运行时或验收状态 |
| Enterprise Agent Range | 新增 `enterprise-agent-range/` 独立靶场设计区：自有 `docs/` 覆盖设计说明、目标范围、企业场景、解耦契约、架构、资产、角色、工具面、攻击分类、场景矩阵、指标、证据、路线、风险、数据模型、数据流和 testcase schema；自有 `status.md` 与 `.log/worklog.md` 已建立 | 当前仅为文档设计；未实现 runtime、mock 业务服务、runner、case fixtures 或报告前端；严格作为独立工作区，不导入 `src/xa_guard`、不复用既有 `docs/`，不改变 L3 验收结论 |

## 本轮性能证据（2026-06-20 实测，commit 432ebbc）

- 进程内六 Gate 500 请求/并发 10：P50 `2.912 ms`、P95 `21.72 ms`、`415.17 QPS`、峰值 RSS `62.59 MB`、530 审计验链通过，四项 PRD 中等档全达标。
- 单进程 Streamable HTTP 10 sessions/500 请求：P95 `169.791 ms`、`74.09 QPS`、峰值 RSS `103.762 MB`、500/500 调用成功、500/500 审计 marker 匹配、关闭后 active=0，全达标。
- 20 sessions/500 请求容量测试：20 会话全部建立/回收、无串话/无审计丢失/验链通过，但 P95 `366.979 ms` > 300ms 门槛 → 如实记录为容量 LIMIT，未声明 20 会话支持。
- 范围：单进程、规则模式、in-process pipeline + Gate6 落盘 / 单 uvicorn worker + 共享 stdio 下游、allow-only；不含 MCP stdio/HTTP 传输、真实模型推理、真实工具耗时、容器网络、多机 soak。

## 未完成的正式验收（BLOCKED 清单）

1. R1 双 500 formal 独立复核 + Gate1 独立 holdout 数据/阈值锁定/Recall/FPR 正式结论 — 需独立评测方。
2. R5 真实 Trae 四案例 + 截图/录像 — 需真实 Trae GUI（按用户指示本轮跳过）。
3. R6 真实 Linux/gVisor runsc 隔离/故障/性能 — Docker build/up + healthz 已 PASS，但 runsc 需 Linux 主机安装（Windows Docker Desktop 无 runsc runtime）。
4. R7 真实 OPA 固定镜像 provenance/license、漂移负测与完整 fixture 矩阵 — parity 与 fail-closed 已 PASS，镜像层未跑。
5. R2/R3 `subscription_budget60_v1` — 离线工具已完成续考与预算安全纠偏；旧首批真实 calibration 因 `$2/$1` 分桶耗尽停在 `$2.94602940`，7/32 complete，冻结失败且不得混入新正式分母。新预算分桶 `$6/$32/$16/$6`，默认 8 jobs/批、失败题 2 次封顶；新的付费校准、AgentDojo suite/arm 批量降本和 sampled 结果未完成。2,986-job `research_full_matrix` 为 `DEFERRED_OPTIONAL`。
6. R8 合法外部 AIBOM 生成器 + 真实 CycloneDX 1.6 产物 + 真实安装链 — 需用户安装/批准外部生成器。
7. R9 第三方 TSA + 真实 HSM/合法 SDK + 故障负测 + faithfulness 大规模独立重放 — 需生产 key/HSM provider（本地 file TSA + 软件 SM2 key 仅为 demo/CI；BUG-R9 已修复，SM2-TSA-token anchor round-trip PASS）。
8. 最终 PDF、视频、表单、截图、原始证据、artifact hash manifest 与外部存证/签名的收束和验收。

## 距离赛题目标

核心安全链路、L3 静态资产和验证入口已具备。R2/R3 的 `subscription_budget60_v1` 离线工程能力现已完成，但新的正式校准和 sampled 结果尚未产生，因此比赛证据仍待完成；2,986-job 全矩阵继续为可选研究扩展。当前仍 BLOCKED：R1 独立双 500/holdout、R2/R3 真实预算型评测、R5 真实 Trae、R6 Linux/runsc、R8 外部 AIBOM、R9 第三方 TSA/HSM，以及最终交付物。仓库状态保持：**L3 静态实现验收通过 + 部分真实验收通过；L3 最终验收 BLOCKED**。
