# XA-Guard 下一步 TODO 与交付收束计划

> 快照时间：**2026-07-15**（Delivery v2 口径）
> 权威交付规格：[../acceptance/DELIVERY-v2.md](../acceptance/DELIVERY-v2.md)
> 仓库状态：[../../status.md](../../status.md)
> 赛题依据：[../source-of-truth/事实源.md](../source-of-truth/事实源.md)

## 0. 先读结论

**活跃口径是 Delivery v2**，不是 L3 最终 BLOCKED 叙事。

- **Tier A（必交）**：D1 PDF、D2 release、D3 视频、D4 报名 — 当前主矛盾。
- **Tier B（主证据）**：B1–B5 均 `DONE`；B6/B7 core fault 7/7 已过，仍待长时故障、性能、UI 与最终 manifest。
- **Tier C（加分）**：R4/R7/R8 已有证据；R2/R3、Trae 截图等为 **RETIRED** 硬承诺，仅背景实验。

**下一步第一优先级**：D2 clean release freeze/final hash；并行完成人工 D4、D1、D3。B6/B7 收口不阻塞最低 D2，但未封存前保持 `PARTIAL`。

---

## 1. Tier A — 官方交付必做

| ID | 任务 | 状态 | 下一步 |
|---|---|---|---|
| A1 | D1 PDF ≤30 页 | `TODO` | 按 [D1 草稿](../delivery/D1-technical-report-draft.md) 写；主实验 = OAR A/B |
| A2 | D2 代码 + README/部署 | `PARTIAL` | release freeze、pytest、verifier、artifact hash |
| A3 | D3 视频 ≤10 分钟 | `TODO` | [D3 脚本](../delivery/D3-video-script.md)；含 OAR 镜头 |
| A4 | D4 报名表审核通过 | `TODO` | 人工确认 `2026.tiaozhanbei.net`；仓库外存证据 |

### A4 报名（人工）

- [ ] 确认系统审核状态为「审核通过」
- [ ] 盖章扫描件与系统信息一致
- [ ] 证据不入 Git（个人隐私）

### A2 D2 release checklist

- [x] `PYTHONUTF8=1 python -m pytest -q`（772 collected / 771 passed / 1 Windows symlink skip）
- [x] `python scripts/verify_l3_static.py --section all`（11/11）
- [x] Reference Docker 六服务 health + PKCE/Undo e2e + core fault 7/7
- [ ] artifact hash manifest
- [ ] README 命令与 D1 一致

---

## 2. Tier B — 产品可信度（OAR 中心）

| ID | 任务 | 状态 | 下一步 |
|---|---|---|---|
| B1 | 六关拦截 demo + MCP e2e + verify_audit | `DONE` | D1/D3 引用现有 trace |
| B2 | OAR 企业 full-day 场景 | `DONE` | D1 §8 描述六域竖切 |
| B3 | Null vs XA-Guard live A/B | `DONE` | D3 展示 `protection_delta` |
| B4 | Ledger replay + audit 对齐 | `DONE` | D1 附 replay JSON 摘要 |
| B5 | 一键 canonical 证据链 | `DONE` | `oar-delivery-v2-20260711T123124Z-win-local` 已封存并锚定 |
| B6 | 可信 Agent Identity | `PARTIAL` | core 身份负测/撤销/跨租户已过；待三账号 UI 与最终 evidence |
| B7 | 可验证 Undo | `PARTIAL` | core 故障/双审批已过；待 Worker long、KEK、性能与最终 manifest |

### B5 封存结果

- [x] Full-day reactive/null 与 live Null/XA-Guard N=3 实跑
- [x] 7/7 attempt replay/hash/ledger/audit 校验
- [x] 标准 run 与 deterministic tarball 封存
- [x] provenance、D1、submission checklist 和[证据总表](../acceptance/EVIDENCE-CONSOLIDATION.md)关联

---

## 3. Tier C — 加分 / 附录（不欠赛题）

| 项 | 状态 | 说明 |
|---|---|---|
| R4 性能 | `DONE` | D1 附录；`docs/evidence/l3-r4-20260705-current/` |
| R7 OPA | `DONE` | D1 附录；注明镜像 CVE |
| R8 cdxgen + install_plugin | `DONE` | 方向 3 附录 |
| R2/R3 budget60 | `RETIRED` | 工具在 `scripts/run_r2_r3_acceptance.py`；背景跑数可选 |
| Trae 截图 | `RETIRED` | 演示用 Cursor pending fallback |
| research_full_matrix | `RETIRED` | 2986 jobs 非 Must |

---

## 4. RETIRED — 不再列为 TODO/BLOCKED

以下 **不得** 出现在执行优先级或 status 缺口中：

- R1 独立 holdout / formal dual-500
- `subscription_budget60_v1` 作为 mandatory 比赛指标
- R9 第三方 TSA/HSM 生产实证
- R8 marketplace/IDE native hooks
- R6 gVisor runsc 全验收（Docker PASS 足够）
- R5 Trae native elicitation
- GB/T 45654 完整 500+ 语料
- enterprise-agent-range 主叙事（OAR 已承接）
- L3 最终验收 BLOCKED 作为项目主状态

---

## 5. 赛题四方向 → 证据映射（写 D1 用）

| 方向 | 主证据（Tier B） | 附录（Tier C） |
|---|---|---|
| 1 输入攻击识别 | Gate1 demo、CSAB-Gov-mini；OAR 注入面 | holdout 协议（RETIRED 正式指标） |
| 2 工具执行安全 | Gate2/3/4/5、OAR seat/SUT、pending | Docker deploy、Trae 静态 |
| 3 供应链 | AIBOM demo、OAR supply consequence | R8 cdxgen |
| 4 评测审计 | **OAR A/B + ledger replay**、Gate6 | R4、R7、bench 工具 |

---

## 6. 建议执行顺序

### 第 0 步（当天）

1. 确认 D4 报名
2. 完成 D1 正文与图表
3. 按 canonical OAR 证据录制 D3

### 第 1 步（不花钱）

1. 全仓 pytest + L3 static verifier
2. D1 正文 + 图表
3. D3 旁白与录屏脚本对齐 D1 数字

### 第 2 步（交付）

1. D1 PDF 导出 ≤30 页
2. D3 剪辑 ≤10 分钟
3. D2 release + submission-checklist
4. 2026-09-15 前邮件提交

---

## 7. 不要做

- 不要把 L3 BLOCKED 或 R2/R3 未跑写成比赛主缺口
- 不要把退役项重新标为 P0 blocker
- 不要修改测试代码掩盖失败
- 不要把 OAR `protection_delta` 写成 AgentDojo 官方 ASR
- 不要把本地 TSA 写成第三方 HSM

---

## 8. 最小完成定义（Delivery v2）

- D4 审核通过
- D1 PDF：四方向 + OAR 主实验 + 诚实限制
- D3 视频：拦截 + 审批/阻断 + 审计 + OAR A/B
- D2：README 可复现 + 测试/verifier 最新结果
- B5：`DONE`，封存 OAR evidence + hash 已具备
- 退役项仅在「限制/未来工作」出现，不作为 blocker

---

## 9. docs 导航

| 文档 | 位置 | 状态 |
|---|---|---|
| DELIVERY-v2 | `docs/acceptance/DELIVERY-v2.md` | `ACTIVE` |
| L3 工程清单 | `docs/acceptance/L3-test-and-acceptance.md` | `DEPRECATED` |
| D1 草稿 | `docs/delivery/D1-technical-report-draft.md` | `TODO` |
| NEXT-WORK-DESIGN | `docs/workplan/NEXT-WORK-DESIGN.md` | `REFERENCE`（待按需同步 v2） |
