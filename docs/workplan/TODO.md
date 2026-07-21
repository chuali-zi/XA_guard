# XA-Guard 下一步 TODO 与交付收束计划

> 快照时间：**2026-07-18**（Delivery v2 口径）
> 权威交付规格：[../acceptance/DELIVERY-v2.md](../acceptance/DELIVERY-v2.md)
> 仓库状态：[../../status.md](../../status.md)
> 赛题依据：[../source-of-truth/事实源.md](../source-of-truth/事实源.md)

## 0. 先读结论

**活跃口径是 Delivery v2**，不是 L3 最终 BLOCKED 叙事。

- **Tier A（必交）**：D4 已完成；D1 PDF、D3 视频按负责人要求暂缓；D2 release 仍为自动收尾主线。
- **Tier B（主证据）**：B1–B5 均 `DONE`；B6/B7 的全故障 11/11、kind HA、签名 evidence 与三账号 UI 已过，正式并发性能未达标。
- **Tier C（加分）**：R4/R7/R8 已有证据；R2/R3、Trae 截图等为 **RETIRED** 硬承诺，仅背景实验。

**下一步自动任务第一优先级**：继续优化或重新设计 Identity + Undo 并发写路径并重跑正式性能；达标后重新封存 evidence，再做 D2 clean release freeze/final hash。统一自动发布 verifier 已通过。D4 与三账号 UI 已完成；D1、D3 标记 `BLOCKED-MANUAL`，在负责人恢复前不推进。

---

## 1. Tier A — 官方交付必做

| ID | 任务 | 状态 | 下一步 |
|---|---|---|---|
| A1 | D1 PDF ≤30 页 | `BLOCKED-MANUAL` | 负责人要求暂缓；恢复后从草稿导出并复核 |
| A2 | D2 代码 + README/部署 | `PARTIAL` | 性能收敛后 release freeze、final verifier、release manifest |
| A3 | D3 视频 ≤10 分钟 | `BLOCKED-MANUAL` | 负责人要求暂缓；恢复后按 D3 脚本录制 |
| A4 | D4 报名表审核通过 | `DONE` | 2026-07-18 负责人确认；隐私证据在仓库外 |

### A4 报名（人工）

- [x] 负责人确认系统审核状态为「审核通过」
- [x] 负责人确认盖章扫描件与系统信息一致
- [x] 证据不入 Git（个人隐私）

### A2 D2 release checklist

- [x] `python scripts/verify_release.py`（2026-07-18：772 collected / 771 passed / 1 Windows symlink capability skip；产品 Ruff、static、Compose、Console、evidence verifier 一并通过）
- [x] `python scripts/verify_l3_static.py --section all`（11/11）
- [x] Reference health + PKCE/Undo e2e + full fault 11/11
- [x] kind 三节点 HA 全阶段 + SM2-with-SM3 evidence verifier
- [ ] 正式 10 并发性能（当前 3/3 失败；Undo latency 10/10 通过）
- [ ] final release manifest（仅 clean final commit 上运行 `scripts/build_release_manifest.py`）
- [x] README 已增加统一 verifier 与 release manifest 命令；提交前仍需与最终 D1 数字复核

---

## 2. Tier B — 产品可信度（OAR 中心）

| ID | 任务 | 状态 | 下一步 |
|---|---|---|---|
| B1 | 六关拦截 demo + MCP e2e + verify_audit | `DONE` | D1/D3 引用现有 trace |
| B2 | OAR 企业 full-day 场景 | `DONE` | D1 §8 描述六域竖切 |
| B3 | Null vs XA-Guard live A/B | `DONE` | D3 展示 `protection_delta` |
| B4 | Ledger replay + audit 对齐 | `DONE` | D1 附 replay JSON 摘要 |
| B5 | 一键 canonical 证据链 | `DONE` | `oar-delivery-v2-20260711T123124Z-win-local` 已封存并锚定 |
| B6 | 可信 Agent Identity | `PARTIAL` | 自动故障、HA、evidence、三账号 UI 已过；待性能达标 |
| B7 | 可验证 Undo | `PARTIAL` | Worker 接管、retry、KEK、Undo 时延已过；写路径性能未达标 |

### B6/B7 最新验收

- [x] Reference 全故障 suite：11/11。
- [x] Worker kill takeover：2 个 Worker actor，1 次有效取消。
- [x] 5/30/120 retry：3 次调度，1 次有效取消。
- [x] 错误 KEK fail closed、admin retry、v1→v2 rewrap 7 条旧记录。
- [x] kind 三节点升级、API/Worker 接管、migration、NetworkPolicy、rollback。
- [x] SM2-with-SM3 封存与独立 verifier。
- [x] Alice/Dora/Admin 三独立会话手测；建票、职责分离、独立批准、补偿和审计内容 PASS。
- [x] 同链进程内预排队减少 connection-pool starvation；开发探针 incremental p95 403.604ms → 206.557ms，未冒充正式通过。
- [ ] 正式 10 并发 incremental p95/upper ≤50ms；当前三轮 p95 352.548/486.272/248.346ms。

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

### 第 0 步（自动，当前）

1. 收敛 Identity + Undo 正式并发性能
2. 性能通过后重跑、重封存、独立验签
3. clean release commit 上重跑统一 verifier 并生成 final release manifest

### 第 1 步（暂缓的人工交付）

1. D1 PDF 导出并人工复核 ≤30 页（`BLOCKED-MANUAL`）
2. D3 录制、剪辑并人工复核 ≤10 分钟（`BLOCKED-MANUAL`）

### 第 2 步（提交）

1. 人工验收结果回填 submission-checklist
2. 核对仓库链接、PDF、视频、报名表和证据包可访问
3. 2026-09-15 前邮件提交

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
| NEXT-WORK-DESIGN | `docs/workplan/NEXT-WORK-DESIGN.md` | `REFERENCE`（2026-07-18 已同步 v2 状态） |
