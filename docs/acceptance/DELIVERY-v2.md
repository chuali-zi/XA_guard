# Delivery v2 · 比赛交付口径（权威）

> **本文档是 XA-Guard 比赛交付的唯一权威口径**（2026-07-11 起生效）。
> 赛题硬门槛见 [事实源 §1.8](../source-of-truth/事实源.md)；工程级 L3 清单见 [L3-test-and-acceptance.md](./L3-test-and-acceptance.md)（**已弃用为比赛承诺**，仅作工程参考）。
> 当前仓库状态见 [status.md](../../status.md)。

---

## 状态图例

| 标签 | 含义 |
|---|---|
| `DONE` | 已有代码、测试或证据，可在声明边界内写入 D1/D2/D3 |
| `PARTIAL` | 主体具备，仍缺正式交付物、冻结证据链或人工事项 |
| `TODO` | 尚未完成，属于当前真实差距 |
| `BLOCKED-MANUAL` | 尚未完成且负责人明确要求暂缓，恢复后必须人工完成 |
| `RETIRED` | 不再作为交付承诺、BLOCKED 项或比赛硬门槛 |

---

## Tier A — 赛题硬门槛（必须提交）

官方依据：[事实源 §1.8](../source-of-truth/事实源.md) · 提交截止 **2026-09-15 24:00**

| ID | 交付物 | 要求 | 状态 | 入口 |
|---|---|---|---|---|
| **A1** | D1 技术方案 PDF | ≤ 30 页 | `DONE` | [D1 正文](../delivery/D1-technical-report-draft.md)；14 页 PDF 位于 `output/pdf/` |
| **A2** | D2 代码 + README/部署 | 可复现原型与运行说明 | `DONE` | [根 README](../../README.md)、`docker-compose.yml`；最终 evidence 与 unified verifier 通过，clean manifest 随冻结提交生成 |
| **A3** | D3 演示视频 | ≤ 10 分钟 | `MANUAL-PENDING` | [逐镜录制指南](../delivery/D3-video-script.md)与 [字幕模板](../delivery/D3-video-subtitles.srt) 已完成；视频由负责人后续录制 |
| **A4** | D4 报名表 | 系统审核通过 + 学校盖章 | `DONE` | 2026-07-18 负责人确认完成；隐私材料在仓库外 |

**Tier A 完成定义**：四件官方材料齐备、可下载/可访问、与邮件提交一致；D2 命令与 D1/D3 叙述一致。

---

## Tier B — 产品可信度（主证据，靶场中心）

**主评测叙事：Open Agent Range（OAR）** — 企业场景 realism、Null vs XA-Guard live A/B、`protection_delta`、ledger replay 与 raw XA-Guard audit 对齐。不以 AgentDojo ASR 或 `subscription_budget60_v1` 作为比赛硬承诺。

| ID | 证据项 | 说明 | 状态 | 证据/入口 |
|---|---|---|---|---|
| **B1** | 六关卡实际拦截 | demo 场景 + MCP e2e + `verify_audit` | `DONE` | `demo/`、`tests/integration/`、`scripts/verify_audit.py` |
| **B2** | 企业场景 realism | Open Agent Range 六域 full-day、多角色业务链 | `DONE` | [open-agent-range/](../../open-agent-range/) |
| **B3** | Null vs XA-Guard live A/B | 真实 `xa_guard.server` session、`protection_delta` | `DONE` | OAR `run-ab --sut-mode null,xaguard --live` |
| **B4** | Ledger replay + audit 对齐 | hash ledger、`replay --verify-sut-audit`、raw XA-Guard audit | `DONE` | OAR `range_cli replay` |
| **B5** | 一键可复现证据链 | 单命令或短脚本产出标准 evidence 目录 | `DONE` | [canonical run 与 hash](./EVIDENCE-CONSOLIDATION.md#2-canonical-主证据) |
| **B6** | 可信 Agent Identity | PKCE 登录、Standard Token Exchange、双主体与动态 assignment | `DONE` | [Identity + Undo 架构](../architecture/agent-identity-and-undo.md)；最终候选全故障 11/11、kind HA、三账号 UI 与正式性能通过 |
| **B7** | 可验证 Undo | PostgreSQL intent、独立审批、六关补偿、业务恢复与事件链 | `DONE` | 最终候选接管/retry/KEK/Undo 时延与正式 3×500 写路径性能通过；最终签名 evidence 收口中 |

### 赛题四方向映射（Tier B 为主叙事）

| 赛题方向 | Tier B 对应 | 支撑能力（非比赛 blocker） |
|---|---|---|
| 1 复杂输入链路攻击识别 | Gate1 demo + CSAB-Gov-mini seed；OAR 注入面 | S1 静态、holdout 协议（`RETIRED` 正式指标） |
| 2 工具调用与任务执行安全 | Gate2/3/4/5 + OAR seat/SUT/ToolSurface + pending/HITL | Trae 静态模板、Docker deploy |
| 3 插件/Skill/脚本供应链 | AIBOM 准入 demo；OAR supply/plugin consequence | R8 cdxgen + `install_plugin`（Tier C） |
| 4 评测、审计与持续优化 | **OAR A/B + ledger replay**；Gate6 SM3/SM2/TSA demo | R4 性能、R7 OPA、bench 工具链 |

### 可复现 OAR 证据命令（canonical）

在仓库根目录，已安装 XA-Guard 依赖且 `PYTHONPATH` 含 `src` 时：

```powershell
cd open-agent-range

# 1) 正常日竖切 + reactive agent（离线 null SUT）
python -m kernel.range_cli day `
  --world scenarios/dctg/full-day.json `
  --agent reactive --sut null `
  --evidence-dir .runtime/delivery-v2-full-day

# 2) replay：hash + ledger + SUT audit 对齐
python -m kernel.range_cli replay `
  --attempt .runtime/delivery-v2-full-day `
  --verify-hashes --verify-ledger --verify-sut-audit --json

# 3) Null vs XA-Guard live A/B（需本机可启动 xa_guard.server）
python -m kernel.range_cli run-ab `
  --finding .runtime/delivery-v2-finding/finding.json `
  --sut-mode null,xaguard --live --repeat 3 --execute `
  --evidence-dir .runtime/delivery-v2-live-ab
```

本轮等价命令已固化为 `oar-delivery-v2-20260711T123124Z-win-local`：标准 run 位于 `D:/xa-evidence/runs/`，sealed tarball SHA-256 为 `cffa89fb2ded79cb17685348bfb6571d85c3c233ad963528ca79b89e2ec49aa5`。完整指标、边界和提交取舍见 [证据收敛总表](./EVIDENCE-CONSOLIDATION.md)。

---

## Tier C — 加分 / 附录（有则更好，不欠赛题）

| ID | 项 | 状态 | 说明 |
|---|---|---|---|
| **C1** | R4 性能 | `DONE` | 进程内 + HTTP 10 会话达标；证据 `docs/evidence/l3-r4-20260705-current/` |
| **C2** | R7 OPA parity | `DONE` | 64 fixtures Python/OPA 一致；镜像扫描有 CVE，生产前需 digest 决策 |
| **C3** | R8 cdxgen + install_plugin | `DONE` | 外部 CycloneDX 1.6 + CLI 准入 + 离线 install_plugin |
| **C4** | R2/R3 server runs | `RETIRED` 作硬承诺 | 预算 runner 保留；可作背景实验 / 附录，不阻塞 Delivery v2 |
| **C5** | Trae 截图 | `RETIRED` 作硬承诺 | 静态模板保留；演示可用 Cursor pending fallback |

---

## 明确退役（不再作为交付承诺或 BLOCKED）

以下项 **不得** 写入 status/TODO/D1 为“待完成 blocker”或“L3 最终 BLOCKED”依据：

| 原编号/概念 | 退役说明 |
|---|---|
| R1 独立 holdout / formal dual-500 | 研究资产保留，不追 formal Recall/FPR |
| `subscription_budget60_v1` 强制指标 | bench 工具保留，非比赛 Must |
| `research_full_matrix` 2986 jobs | 可选研究扩展 |
| R9 第三方 TSA/HSM | 本地 SM2/TSA demo 足够；external bridge 为加分 |
| R8 marketplace/IDE hooks | 离线准入已够方向 3 叙事 |
| R6 Part B gVisor runsc 全验收 | Docker deploy + healthz PASS 即够部署叙事 |
| R5 Trae native elicitation | pending fallback / Cursor 主演示 |
| 外部 notarization for final-report | 本地 hash manifest 即可 |
| GB/T 45654 完整 500+ 语料 | CSAB-Gov-mini 290 为 PoC 缩减版 |
| `enterprise-agent-range` 主叙事 | 能力已并入 OAR；仅附录提及或省略 |

---

## 诚实边界（写入 D1 §10 / status）

- **OAR** 是红队竖切与证据链中心，不是完整工业级 7×24 在线沙盘；ReactiveSeat 为确定性状态机，非任意长度 live agent。
- **XA-Guard 主产品**：六关 + 审计 + AIBOM + Docker 部署已可演示；20 会话 HTTP 容量为 LIMIT，不宣称生产容量。
- **Identity + Undo**：Reference 最终候选全故障 11/11、kind HA profile 和正式 10 并发三轮性能通过；完整重建组 p95/upper 为 45.109/46.984、42.141/43.120、43.934/45.528ms。它仍不是生产 IAM、生产多地域 HA、绝对 exactly-once 或通用数据库回滚。
- **人工交付**：D4 与三账号 UI 已由负责人确认完成；D1 PDF 已生成；D3 录制指南与字幕模板已完成，最终视频仍由负责人手工录制。D2 最终 evidence 与 unified verifier 已通过，本地冻结提交与 clean manifest 在本次收口完成。B5 canonical OAR 证据已封存。
- **L3 文档**：`L3-test-and-acceptance.md` 中的 R2–R9 BLOCKED 语言描述的是**历史工程验收面**，不是 Delivery v2 比赛缺口。

---

## 交叉链接

| 文档 | 用途 |
|---|---|
| [status.md](../../status.md) | 当前仓库状态（Delivery v2 口径） |
| [TODO.md](../workplan/TODO.md) | 执行优先级 Tier A/B/C |
| [D1 草稿](../delivery/D1-technical-report-draft.md) | 技术方案正文 |
| [D3 脚本](../delivery/D3-video-script.md) | 演示视频 |
| [submission-checklist.md](../delivery/submission-checklist.md) | 提交包 |
| [EVIDENCE-CONSOLIDATION.md](./EVIDENCE-CONSOLIDATION.md) | 证据总表、哈希、边界与提交取舍 |
| [事实源](../source-of-truth/事实源.md) | 赛题官方事实 |
| [L3-test-and-acceptance.md](./L3-test-and-acceptance.md) | 工程验收参考（已弃用为比赛承诺） |
| [open-agent-range/status.md](../../open-agent-range/status.md) | OAR 子项目状态 |

---

*维护：交付口径变更时同步更新本文、`status.md` 与 `log.md` 顶条；勿将退役项重新标为 BLOCKED。*
