# 仓库状态：XA-Guard / XA-202620

> 快照日期：**2026-07-12**
> **活跃口径**：[docs/acceptance/DELIVERY-v2.md](docs/acceptance/DELIVERY-v2.md)（Tier A/B/C + 退役清单）
> 工程参考（非比赛承诺）：[docs/acceptance/L3-test-and-acceptance.md](docs/acceptance/L3-test-and-acceptance.md)
> 本文件仅描述当前仓库状态与真实差距，不记录工作历史（见 [log.md](log.md)）。

---

## 总体结论

仓库已达到 **XA-Guard 核心产品可演示 + 工程验收资产齐备 + Open Agent Range 主评测证据可复现** 的状态。

- **主评测叙事**：Open Agent Range（OAR）企业场景竖切、Null vs XA-Guard live A/B、`protection_delta`、ledger replay 与 raw XA-Guard audit 对齐——见 [DELIVERY-v2 Tier B](docs/acceptance/DELIVERY-v2.md#tier-b--产品可信度主证据靶场中心)。
- **不再使用**「L3 最终验收 BLOCKED」作为项目主状态；历史 L3 R2–R9 BLOCKED 语言仅描述工程验收面，多数项已 **RETIRED** 为比赛硬承诺（见 DELIVERY-v2 退役表）。
- **真实差距（Tier A）**：D1 PDF、D2 clean release freeze、D3 视频、D4 报名证据。B5 canonical OAR 证据链已封存。
- **正式新增（默认关闭）**：可信双主体 Agent Identity + 补偿式 Undo 已从两轮竖切迁入 `src/xa_guard` 正式运行路径；提供 JWT/JWKS HTTP/stdio 身份绑定、加密 EffectStore、职责分离审批、六关补偿、业务工单 cancel 适配和生产配置模板。上线仍需接入真实 IdP/JWKS、密钥管理和业务环境验收。

GitHub Actions 双 Python 质量门禁历史通过（Linux 3.10/3.12）。本轮本机全仓 673 collected，672 passed、1 skipped（仅因缺少 `xa-guard/sandbox:latest`）；CI 口径 Ruff PASS，L3 static verifier 11/11 sections PASS。完整证据状态见 [证据收敛总表](docs/acceptance/EVIDENCE-CONSOLIDATION.md)。

Identity + Undo 受影响范围 68 passed；OAR 非默认收集测试 33 passed。全仓首轮发现 ChainStore Windows 多进程低概率断链，未修改测试，已将权威尾校验从不可靠的 size/mtime 判据改为锁内 O(末行)读取，并允许 Windows audit rotation；最终实现完整 Merkle/归档 12 passed、并发压力额外 10/10 轮通过、500 条基准约 1151 records/s，随后全仓回归通过。详见 [正式接入验证](docs/evidence/agent-identity-undo-formal-2026-07-12/README.md)。

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
| Agent Identity + Undo | `IMPLEMENTED / DEFAULT-OFF` | 正式 HTTP/stdio JWT/JWKS 绑定、AES-GCM SQLite、幂等/租户隔离/职责分离、六关补偿已接入；非通用数据库回滚，多地域/KMS/真实 IdP 待部署验收 |
| 审计链 SM3/SM2/TSA/faithfulness | `DONE` | 本地 TSA/软件 key；第三方 TSA 为 Tier C/RETIRED |
| Docker Compose + healthz | `DONE` | R6 Docker 部署 PASS；远端 system Docker + gVisor runsc PASS 已回传并锚定，rootless runsc LIMIT；gVisor runsc 全验收不作比赛硬承诺 |
| OPA Gate3 parity | `DONE` | 64 fixtures 一致；默认镜像有 CVE 发现 |
| AIBOM + 外部 cdxgen | `DONE` | marketplace/IDE hook RETIRED |
| CSAB-Gov-mini / bench 工具 | `DONE` | 290 seed；非国标完整 500+ 语料 |
| R4 性能 | `DONE` | 10 会话达标；20 会话 LIMIT |
| 全仓测试 | `DONE / 1 ENV SKIP` | 673 collected，672 passed；仅本机缺 sandbox 镜像 skip，非代码失败 |

---

## Open Agent Range（主评测叙事）

独立目录 [open-agent-range/](open-agent-range/)：PRD 冻结；SP2+ full-day 六域竖切；ReactiveSeat；attempt 级真实 `xa_guard.server` live session；canonical N=3 中 Null 3/3 泄漏、XA-Guard 3/3 拦截、0 infra error、`protection_delta=1.0`；7/7 attempt replay 通过，XA-Guard 侧 ledger 与 raw audit 逐序对齐；workbench HTTP 可 manual-session / A/B / evidence review。

**边界**：非完整工业级在线沙盘；ReactiveSeat 为确定性状态机；F15 等为最小落点。细节见 [open-agent-range/status.md](open-agent-range/status.md)。

2026-07-12 新增隔离 feasibility experiment：Ed25519 双主体签名身份的 4 类负测均在 executor 前拒绝；
`update_registry` 原动作与第二主体补偿均经过真实 XA-Guard Pipeline 并恢复前态；`send_message` 如实标记为不可逆；
Gate6/OAR 两条 hash chain 均通过。证据见
[agent-identity-undo-spike-2026-07-12](docs/evidence/agent-identity-undo-spike-2026-07-12/README.md)。
第一轮未实现 HTTP 身份入口、加密 EffectStore、重启恢复或并发控制；这些可行性问题由下述第二轮继续验证。

第二轮进一步通过实验性 MCP Bearer middleware 保护真实 Streamable HTTP session：缺/坏 token 为 401，身份冲突和 tool scope 越权为 403，拒绝路径下游零执行；
EffectRecord 使用 AES-GCM 加密写入 SQLite，重新创建 store 后可恢复，错误密钥拒绝，幂等申请稳定，两个独立 store 并发 claim 只有一个成功；
Carol 通过独立 Bearer session 补偿并恢复世界前态。证据见
[agent-identity-undo-spike-round2-2026-07-12](docs/evidence/agent-identity-undo-spike-round2-2026-07-12/README.md)。
上述实验结论现已产品化进入正式 HTTP/stdio 入口、GateContext/Gate6 schema、业务 API 连接器、配置与回归测试。正式实现见
[Agent Identity 与 Undo 架构](docs/architecture/agent-identity-and-undo.md) 和
[`configs/xa-guard.identity-undo.yaml`](configs/xa-guard.identity-undo.yaml)。仍未完成真实政企 IdP 联调、JWKS 轮换演练、KMS/HSM 托管、多地域一致性与补偿失败调度。

Auto-RedTeam Conductor 与持续运行维护层已联调运行：外层提案固定 Codex `gpt-5.6-sol`，OAR 内部 OpenCodeSeat 默认 `deepseek/deepseek-v4-flash`；维护器 PID/进度监控、异常恢复、退避熔断、持久 stop/resume、陈旧锁恢复和连续业务错误熔断可用。mailbox/rag/ticket/rag-index 已生成 proposal/finding、完成 Null vs XA-Guard A/B 并封存为诚实 `LIMIT`；后续 tool-args 尝试为 `INFRA_ERROR`，没有冒充 finding。本地 maintainer 已正常完成。Conductor merge 与 maintenance 修正已进入发布分支，仍需远端 PR 合并后才属于默认分支发布能力。

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
- Identity + Undo 可行性：[docs/planning/agent-identity-undo-feasibility.md](docs/planning/agent-identity-undo-feasibility.md)
- Identity + Undo 第二轮：[docs/planning/agent-identity-undo-feasibility-round2.md](docs/planning/agent-identity-undo-feasibility-round2.md)
- Identity + Undo 正式架构：[docs/architecture/agent-identity-and-undo.md](docs/architecture/agent-identity-and-undo.md)
