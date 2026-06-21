# 仓库状态：XA-Guard / XA-202620

> 快照日期：2026-06-21（仓库环境）
> 本文件仅描述当前仓库状态、验收边界与剩余差距，不记录工作历史。
> 2026-06-20 已在 commit `432ebbc` 实跑 L3 静态验收 S1–S7（全 PASS，123 测试）与能力范围内真实验收 R2/R3/R4/R6/R7/R9；证据目录 `D:/evidence/l3-20260620T090452Z/`（final-report.json + artifact-hashes.json 149 文件）。R6 Docker build/up+healthz 已 PASS（gVisor runsc 仍 BLOCKED，Windows 无 runsc）。BUG-R9 已修复+回归测试。仍 BLOCKED：R1 独立双 500/holdout、R2/R3 完整 ASR 矩阵、R5 真实 Trae GUI、R6 gVisor runsc（需 Linux）、R8 外部 AIBOM 生成器、R9 第三方 TSA/HSM。
> 2026-06-21 对 commit `6cf1ce9` 复核：统一静态 verifier `11/11` sections PASS；全量 pytest 在默认 Windows/CP1252 子进程环境为 `561 passed, 1 failed, 1 skipped`，总覆盖率 `79%`。唯一失败是 `validate_csab_gov_mini.py` 输出 Unicode 箭头触发 `UnicodeEncodeError`，设置 `PYTHONUTF8=1` 后该用例通过；唯一 skip 是本机缺 `xa-guard/sandbox:latest` 测试镜像。故当前不能写”默认环境全量测试全绿”。
> 2026-06-21 R2/R3 正式矩阵 smoke：4-job 真实 `opencode run` 调用完成（4/4 status=complete，resume skip 验证通过），模型 `opencode-go/glm-5.2`，证据 `D:/evidence/r2-r3-20260621b/`。完整 2,986-job 矩阵**等待用户确认预算**（预估 ~$289 / ~99 小时）。

## 总体结论

仓库已达到 **L3 静态实现验收通过 + L3 核心工程原型可运行 + 部分真实环境验收通过**：
- 静态 S1–S7 全部 PASS（双 500 implementation、Gate1 holdout 协议、AgentDojo/InjecAgent runner、性能入口、Trae/gVisor/OPA 静态、AIBOM/国密/审计/faithfulness 单测；S7 含 BUG-R9 回归测试 123 passed）。
- 真实验收已通过：R4 性能（进程内 500 + HTTP 10 会话/500，四项 PRD 中等档全达标）、R6 Docker build/up + healthz（6/6 steps PASS，容器 live healthy）、R7 OPA parity（真实 OPA 1.17.0 与 Python fallback 7/7 一致 + strict_opa fail-closed 确认）、R2 install_plugin + AgentDojo baseline + InjecAgent base/defended 真实 opencode smoke（官方上游 pinned，official_claim=False）、R9 本地 SM2-with-SM3 签验 + 篡改检出 + faithfulness 独立重算 + 本地 TSA anchor（含 SM2-TSA-token 路径，BUG-R9 修复后 PASS）。
- 20 会话容量如实记录为 LIMIT（P95 366.979ms > 300ms），未声明支持。
- BUG-R9（SM2-TSA-token anchor 验证 mismatch）已修复：`tsa.py` `_payload_for_hash` 排除 `sm2_tsa_*` 字段，新增回归测试，S7 全套 123 passed 无回归。
- BUG-R9 修复及回归测试已进入 commit `6cf1ce9`，本快照随之同步。2026-06-21 全量测试默认 Windows 编码下还有 1 个可复现兼容性失败。

当前仍**不能宣称“L3 最终验收通过”或“赛题最终达标”**。剩余差距：R1 正式双 500/holdout 独立评测、R2/R3 完整 ASR 矩阵、R5 真实 Trae GUI、R6 真实 Linux/gVisor runsc 隔离、R8 外部 AIBOM 生成器、R9 第三方 TSA/HSM。

按 PRD 的 D2 代码交付清单看，README、Compose、79% 覆盖率、六关测试、31 条 Gate3 baseline 规则、审计实现和 Apache-2.0 LICENSE 已具备；公开 remote 已配置，但真实 Trae 验收仍缺。按更严格的 `docs/L3-test-and-acceptance.md` 最终口径，R1/R2/R3/R5/R6/R8/R9 仍有必验项 BLOCKED，因此整体判定仍为 **BLOCKED，而非 PASS**。仓库内也未发现 D1 技术方案成稿、D3 演示视频或 D4 报名材料；这不影响代码静态 L3，但影响赛题完整交付。

## 当前实现快照

| 验收面 | 当前状态 | 边界 |
|---|---|---|
| L3 static-only (S1–S7) | 2026-06-20 实跑全 PASS：S1 双 500 implementation + formal 负测、S2 holdout 协议 8 测、S3 runner 9 测、S4 性能入口 7 测、S5 Trae 3/3、S6 compose+gVisor/OPA/deployment+17 测+OPA bundle、S7 修复后 123 测 | 静态 PASS 不等于最终验收 PASS；BUG-R9 修复现已进入 `6cf1ce9` |
| 当前全仓测试/覆盖率 | 2026-06-21：默认环境 `561 passed, 1 failed, 1 skipped`；覆盖率 `79%`；`PYTHONUTF8=1` 后失败用例单独 PASS；统一静态 verifier 11/11 PASS | 默认 Windows/CP1252 下校验脚本输出 Unicode 箭头失败；sandbox 镜像测试 skip，不能宣称全绿 |
| 双 500 语料 (R1) | implementation profile 500+500、1000 唯一 payload、17 类各≥29 已实测验过；formal 正确非零退出 | formal 所需独立 attestation/taxonomy/semantic-group 复核 BLOCKED，不能作为正式双 500 |
| Decision faithfulness (R9c) | 本轮 25 条真实签名审计独立重算 100% 一致；直接函数验证非固定 1.0（不一致 deny→0.45） | 真实 agent trace 的大规模独立重放未完成 |
| LangChain / LangGraph | wrapper、callback/observer、HITL resume、node/tool 等适配已实现 | 固定真实版本及真实 agent/transport 端到端验收未完成 |
| Trae (R5) | 配置模板、接入文档和 allow/deny/taint/pending 四案例静态资产 S5 PASS | 真实 Trae GUI 工具发现/调用/HITL/日志/截图 BLOCKED（按用户指示跳过 GUI） |
| gVisor (R6) | 静态 runsc/禁网/只读根/非 root/cap_drop/no-new-priv/资源限制 S6 验过；**Docker build/up + healthz 真实 PASS（6/6 steps，容器 live healthy，镜像 xa-guard:latest+sandbox:latest 构建成功）** | 真实 Linux/runsc 隔离 BLOCKED：Windows Docker Desktop 无 runsc runtime（runtimes=[runc,containerd,nvidia]），需 Linux 主机 |
| OPA (R7) | 本轮真实 OPA 1.17.0 与 Python fallback 7/7 parity；strict_opa fail-closed 在 gate3_policy.py:59-60 确认 | 真实 OPA 固定镜像 provenance/license、漂移负测与完整 fixture 矩阵未跑 |
| AIBOM (R2/R8) | 内部扫描/评级/签名/漂移/离线 preflight S7 测过；真实 opencode install_plugin smoke PASS（AIBOM F deny） | 合法外部生成器真实产物/marketplace/IDE 安装链 BLOCKED |
| 审计与国密 (R9) | 本轮真实 SM2-with-SM3 签验 25 条 0 错误 + 篡改检出；本地 TSA anchor（**含 SM2-TSA-token 路径，BUG-R9 修复后 PASS**）验过；faithfulness 重算 PASS | 第三方 TSA/HSM BLOCKED（本地 file TSA + 软件 SM2 key 仅为 demo/CI） |
| 外部 benchmark (R2/R3) | 统一矩阵 orchestrator（plan/run/resume/aggregate/verify）已实现；15 个离线测试 PASS；**4-job 真实 smoke 完成**：workspace suite baseline/defended 配对，模型 `opencode-go/glm-5.2`，4/4 status=complete，resume skip 验证通过；证据目录 `D:/evidence/r2-r3-20260621b/`（matrix-plan.json + jobs/*/result.json + state.json + logs/*） | 完整 2,986-job 矩阵**等待用户确认预算**（预估 ~17,916 次调用 / ~$289 / ~99 小时）；aggregate/verify 未执行（矩阵不完整时 aggregate 必定 FAIL，属预期行为） |
| 性能 (R4) | 本轮实测：进程内 500 P50 2.912ms/P95 21.72ms/QPS 415.17/RSS 62.59MB；HTTP 10×500 P95 169.79ms/QPS 74.09/RSS 103.76MB、500/500 审计 marker 匹配，全达标 | 20 会话容量 LIMIT（P95 366.979ms > 300ms，未声明支持）；多 worker/TLS/多机 soak 未跑 |

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
5. R2 完整 AgentDojo ASR 矩阵 + R3 完整 InjecAgent 510 DH + 544 DS — **4-job smoke 已通过**（workspace suite），完整 2,986-job 矩阵等待用户确认预算（~$289 / ~99h）。
6. R8 合法外部 AIBOM 生成器 + 真实 CycloneDX 1.6 产物 + 真实安装链 — 需用户安装/批准外部生成器。
7. R9 第三方 TSA + 真实 HSM/合法 SDK + 故障负测 + faithfulness 大规模独立重放 — 需生产 key/HSM provider（本地 file TSA + 软件 SM2 key 仅为 demo/CI；BUG-R9 已修复，SM2-TSA-token anchor round-trip PASS）。
8. 最终 PDF、视频、表单、截图、原始证据、artifact hash manifest 与外部存证/签名的收束和验收。

## 距离赛题目标

核心安全链路、L3 静态资产和验证入口已具备；2026-06-20 的证据显示 S1–S7 静态验收通过，并完成 R4 性能、R6 Docker build/up + healthz、R7 OPA parity、R2/R3 单例 smoke、R9 本地密码与审计验证。20 会话为容量 LIMIT。2026-06-21 R2/R3 正式矩阵 4-job smoke 完成（baseline/defended 配对、resume skip 验证通过），完整 2,986-job 矩阵等待用户确认预算。当前仍 BLOCKED：R1 独立双 500/holdout、R2/R3 完整矩阵（待预算确认）、R5 真实 Trae、R6 Linux/runsc、R8 外部 AIBOM、R9 第三方 TSA/HSM；另有默认 Windows 编码测试失败。满足全部必验项前，仓库状态保持：**L3 静态实现验收通过 + 部分真实验收通过；L3 最终验收 BLOCKED**。完整历史证据见 `D:/evidence/l3-20260620T090452Z/final-report.json`，R2/R3 smoke 证据见 `D:/evidence/r2-r3-20260621b/`。
