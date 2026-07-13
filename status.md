# 仓库状态：XA-Guard / XA-202620

> 快照日期：**2026-07-11**
> **活跃口径**：[docs/acceptance/DELIVERY-v2.md](docs/acceptance/DELIVERY-v2.md)（Tier A/B/C + 退役清单）
> 工程参考（非比赛承诺）：[docs/acceptance/L3-test-and-acceptance.md](docs/acceptance/L3-test-and-acceptance.md)
> 本文件仅描述当前仓库状态与真实差距，不记录工作历史（见 [log.md](log.md)）。

---

## 总体结论

仓库已达到 **XA-Guard 核心产品可演示 + 工程验收资产齐备 + Open Agent Range 主评测证据可复现** 的状态。

- **主评测叙事**：Open Agent Range（OAR）企业场景竖切、Null vs XA-Guard live A/B、`protection_delta`、ledger replay 与 raw XA-Guard audit 对齐——见 [DELIVERY-v2 Tier B](docs/acceptance/DELIVERY-v2.md#tier-b--产品可信度主证据靶场中心)。
- **不再使用**「L3 最终验收 BLOCKED」作为项目主状态；历史 L3 R2–R9 BLOCKED 语言仅描述工程验收面，多数项已 **RETIRED** 为比赛硬承诺（见 DELIVERY-v2 退役表）。
- **真实差距（Tier A）**：D1 PDF、D2 clean release freeze、D3 视频、D4 报名证据。B5 canonical OAR 证据链已封存。

GitHub Actions 双 Python 质量门禁已通过（Linux 3.10/3.12）。本轮 Ruff PASS；全仓 667 collected，666 passed、1 skipped（本机无 sandbox image）；static verifier 11/11 PASS。完整证据状态见 [证据收敛总表](docs/acceptance/EVIDENCE-CONSOLIDATION.md)。

---

## Delivery v2 状态一览

| 层级 | 项 | 状态 | 说明 |
|---|---|---|---|
| **Tier A** | D1 PDF ≤30 页 | `TODO` | 草稿 [docs/delivery/D1-technical-report-draft.md](docs/delivery/D1-technical-report-draft.md) |
| **Tier A** | D2 代码 + README/部署 | `PARTIAL` | 六关、Compose、测试、README 具备；release freeze 与最终 hash 待做 |
| **Tier A** | D3 视频 ≤10 分钟 | `TODO` | 脚本 [docs/delivery/D3-video-script.md](docs/delivery/D3-video-script.md) |
| **Tier A** | D4 报名 | `TODO` | 仓库无审核通过证据；人工确认 |
| **Tier B** | B1 六关拦截 | `DONE` | demo + MCP e2e + `verify_audit` |
| **Tier B** | B2 OAR 企业场景 | `DONE` | full-day 六域、多角色业务链 |
| **Tier B** | B3 live A/B | `DONE` | `null,xaguard --live --repeat 3`，`protection_delta=1.0` |
| **Tier B** | B4 ledger + audit 对齐 | `DONE` | `replay --verify-sut-audit` |
| **Tier B** | B5 一键证据链 | `DONE` | canonical OAR N=3 已标准封存并写入 provenance |
| **Tier C** | R4 性能 | `DONE` | 支持 D1 附录 |
| **Tier C** | R7 OPA | `DONE` | 支持 D1 附录；镜像 CVE 需风险接受说明 |
| **Tier C** | R8 cdxgen + install_plugin | `DONE` | 支持方向 3 附录 |
| **Tier C** | R2/R3 budget60 | `RETIRED` | 工具保留，背景实验可选 |
| **RETIRED** | R1 holdout / dual-500 | `RETIRED` | 研究资产 |
| **RETIRED** | R5 Trae GUI / R6 runsc / R9 第三方 TSA/HSM 等 | `RETIRED` | 见 DELIVERY-v2 退役表；R6 system runsc 远端附录证据已采集，rootless runsc 为 LIMIT |

---

## XA-Guard 主产品能力（支撑证据，非比赛 blocker）

| 能力面 | 状态 | 边界 |
|---|---|---|
| 六关卡 pipeline（Gate1–6） | `DONE` | L3 静态 S1–S7 历史 PASS；MCP e2e、压力测试已覆盖 |
| Agent Governance v1 | `DONE` | 默认关闭；本地治理预检，非生产 IAM |
| 审计链 SM3/SM2/TSA/faithfulness | `DONE` | 本地 TSA/软件 key；第三方 TSA 为 Tier C/RETIRED |
| Docker Compose + healthz | `DONE` | R6 Docker 部署 PASS；远端 system Docker + gVisor runsc PASS 已回传并锚定，rootless runsc LIMIT；gVisor runsc 全验收不作比赛硬承诺 |
| OPA Gate3 parity | `DONE` | 64 fixtures 一致；默认镜像有 CVE 发现 |
| AIBOM + 外部 cdxgen | `DONE` | marketplace/IDE hook RETIRED |
| CSAB-Gov-mini / bench 工具 | `DONE` | 290 seed；非国标完整 500+ 语料 |
| R4 性能 | `DONE` | 10 会话达标；20 会话 LIMIT |
| 全仓测试 | `PARTIAL` | 历史记录全绿；sandbox 镜像本机可能 skip |

---

## Open Agent Range（主评测叙事）

独立目录 [open-agent-range/](open-agent-range/)：PRD 冻结；SP2+ full-day 六域竖切；ReactiveSeat；attempt 级真实 `xa_guard.server` live session；canonical N=3 中 Null 3/3 泄漏、XA-Guard 3/3 拦截、0 infra error、`protection_delta=1.0`；7/7 attempt replay 通过，XA-Guard 侧 ledger 与 raw audit 逐序对齐；workbench HTTP 可 manual-session / A/B / evidence review。

**边界**：非完整工业级在线沙盘；ReactiveSeat 为确定性状态机；F15 等为最小落点。细节见 [open-agent-range/status.md](open-agent-range/status.md)。

Auto-RedTeam 持续运行维护层已在当前工作树实现并通过 6 项离线测试，具备进程/进度健康检查、异常恢复、退避熔断、持久 stop/resume 与状态落盘，且维护心跳不会冒充业务进度；但完整 Conductor 源码仍只在未合并的 `feat/cursor-auto-redteam`，因此当前 `main` 尚不能宣称端到端持续自动红队可运行。

**enterprise-agent-range/** 为早期独立设计区，能力已主要由 OAR 承接；不作为主叙事。

---

## 剩余真实差距（非退役项）

1. **D1**：30 页 PDF 成稿（OAR A/B + 六关 demo 为主实验）。
2. **D3**：≤10 分钟视频（拦截、审批/阻断、审计、OAR 镜头）。
3. **D4**：报名系统审核通过证据（人工）。
4. **D2 release**：clean worktree、final commit/hash manifest、与 D1 命令一致。

可选 Tier C：R2/R3 背景跑数、Trae 截图——不阻塞提交。

---

## 距离赛题官方要求

按 [事实源 §1.8](docs/source-of-truth/事实源.md)：四件必交材料中 **D2 主体已具备**，**D1/D3/D4 未完成**；可选补充（评测脚本、攻击样例、审计样例）可从 OAR evidence 与 `verify_audit` 组装。

评分维度上：**实际效果** 靠 OAR A/B + 六关 live demo；**技术创新** 靠 Agent Gateway + 六关 + 国密审计 + OAR 靶场；**方案完整性** 靠四方向映射与 DELIVERY-v2 诚实验边界；**展示表达** 靠 D3。

---

## 文档入口

- 交付口径：[docs/acceptance/DELIVERY-v2.md](docs/acceptance/DELIVERY-v2.md)
- 证据总表：[docs/acceptance/EVIDENCE-CONSOLIDATION.md](docs/acceptance/EVIDENCE-CONSOLIDATION.md)
- 执行 TODO：[docs/workplan/TODO.md](docs/workplan/TODO.md)
- 文档导航：[docs/README.md](docs/README.md)
