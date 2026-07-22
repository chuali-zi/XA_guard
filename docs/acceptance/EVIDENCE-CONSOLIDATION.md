# XA-Guard 证据收敛总表

> 快照：2026-07-21（America/Los_Angeles）。
> 交付权威口径：[DELIVERY-v2.md](./DELIVERY-v2.md)。
> 机器索引：[../evidence/EVIDENCE-INDEX.json](../evidence/EVIDENCE-INDEX.json)。
> sealed 信任锚：[remote-evidence/PROVENANCE.md](./remote-evidence/PROVENANCE.md)。

## 1. 收敛结论

比赛产品证据已收敛为一条 OAR 主链、一组 Identity + Undo 当前证据和四组附录：

1. **主链**：OAR full-day + live Null/XA-Guard N=3 A/B + replay/audit alignment，已标准封存。
2. **产品闭环**：六关 demo、MCP e2e、Gate6 audit 与当前全仓测试。
3. **工程附录**：R4 性能、R7 OPA、R8 AIBOM、R6 system runsc。
4. **密码审计附录**：R9 本地 SM3/SM2/anchor 为 `LIMIT`，仅作 demo，不宣称第三方 TSA/HSM。
5. **Identity + Undo**：最终候选 Reference 全故障 11/11、kind HA 与正式并发性能通过；[最终 evidence](../evidence/agent-identity-undo-final-2026-07-21.md) 已以 SM2-with-SM3 封存并独立验签通过。
6. **历史研究资产**：旧 L3、R2/R3、Enterprise Agent Range 和分散 `.runtime`，不进入比赛主结论。

Identity + Undo 三账号浏览器业务闭环于 2026-07-18 由负责人手测 PASS；2026-07-21 最终候选全故障 11/11、kind HA 全阶段和正式性能通过。交付自动项只剩最终 evidence、unified verifier 与 clean manifest；D1 PDF 已完成，D3 指南/字幕完成但视频仍需负责人录制。

## 2. Canonical 主证据

| 项 | 值 |
|---|---|
| run id | `oar-delivery-v2-20260711T123124Z-win-local` |
| 完整 run | `D:/xa-evidence/runs/oar-delivery-v2-20260711T123124Z-win-local/` |
| sealed 包 | `D:/xa-evidence/sealed/oar-delivery-v2-20260711T123124Z-win-local.tar.gz` |
| tarball SHA-256 | `cffa89fb2ded79cb17685348bfb6571d85c3c233ad963528ca79b89e2ec49aa5` |
| 封存规模 | 127 files / 451499 bytes；tarball 78889 bytes |
| 源代码 commit | `c68c4be7ed4899c2fcdab556c45fc9bcc2b67cb5`，工作树 dirty 状态与路径见包内 `meta.json` |
| 结果 | `PASS`（限下述实验范围） |

### 2.1 Full-day

- `scenarios/dctg/full-day.json`，ReactiveSeat，null SUT。
- 41 次工具尝试、43 条 ledger、0 违规、hash chain OK。
- replay 检查 15 项 artifact hash，ledger projection 与 41 个 tool-event/range-audit 顺序一致。

### 2.2 Live A/B

- 同一 mailbox finding，真实本地 `xa_guard.server` stdio MCP，3 个独立 attempt。
- Null：3/3 泄漏 synthetic data ref `cit-1001`。
- XA-Guard：3/3 拦截，0 protected infra error。
- `asr_null=1.0`、`asr_protected=0.0`、`protection_delta=1.0`。
- 每个 XA-Guard attempt：19 项 artifact hash；3 tool events、3 range audit、3 ledger attempts/decisions、3 raw XA-Guard audit 逐序对齐。

上述数字只描述这个确定性 finding 的 N=3 本地实验，不外推为公开 benchmark、生产 ASR 或统计总体效果。

## 3. 官方交付映射

| 交付项 | 状态 | 当前证据 | 尚需动作 |
|---|---|---|---|
| D1 技术方案 PDF <=30 页 | `DONE` | [D1 正文](../delivery/D1-technical-report-draft.md) 与 `output/pdf/` 14 页成品 | 提交前核对附件 |
| D2 代码 + README/部署 | `DONE` | README、Compose；2026-07-21 最终统一验证 782 collected / 781 passed / 1 Windows symlink capability skip；产品 Ruff、static 11/11、Console、最终 evidence verifier PASS | 本地冻结提交后生成 clean release manifest |
| D3 演示视频 <=10 分钟 | `MANUAL-PENDING` | [逐镜录制指南](../delivery/D3-video-script.md)与字幕模板已完成 | 负责人录制、剪辑和复核 |
| D4 审核通过报名表 | `DONE` | 2026-07-18 负责人确认审核与盖章已完成；隐私材料不入仓库 | 提交时从仓库外附件位置取用 |

## 4. Tier B 产品证据映射

| ID | 状态 | 证据与结论 |
|---|---|---|
| B1 六关拦截 | `DONE` | `demo/`、`tests/integration/test_mcp_e2e.py`、`scripts/verify_audit.py`；全仓测试本轮通过（1 个 Docker image skip） |
| B2 企业场景 | `DONE` | canonical full-day：六域、41 tool attempts、43 ledger、0 violations |
| B3 live A/B | `DONE` | canonical N=3：Null 3/3 leak、XA-Guard 3/3 block、0 infra error、delta 1.0 |
| B4 replay/audit | `DONE` | 7/7 attempt replay PASS；XA-Guard 侧 raw audit 逐序对齐 |
| B5 一键证据链 | `DONE` | 标准 run + deterministic tar.gz + SHA-256 + git provenance 记录；提交/推送后形成远端信任锚 |
| B6 可信 Agent Identity | `DONE` | 最终候选 Reference 全故障 11/11、kind HA、三账号 UI 与正式性能通过 |
| B7 可验证 Undo | `DONE` | Worker 接管、retry、KEK、Undo latency 与正式写路径性能通过；最终 14-artifact evidence 独立验签通过 |

## 5. Tier C 与支撑证据

| 证据 | 位置 | 校验 | 可声明边界 |
|---|---|---|---|
| R4 性能 | `docs/evidence/l3-r4-20260705-current/` | 8/8 artifact hashes PASS | 10 sessions/500 PASS；20 sessions LIMIT；本地单进程 |
| R7 OPA | `D:/evidence/l3-r7-20260706T055152Z/` | 20/20 hashes PASS | 64 fixtures parity；镜像扫描有 2 critical/26 high，需风险接受或换 digest |
| R8 AIBOM | `docs/acceptance/r8-aibom-external/evidence/l3-r8-aibom-20260707T105519Z/` | 7/7 hashes PASS | cdxgen 12.7.0 / CycloneDX 1.6 / MCP 语义；非 marketplace 原生链 |
| R6 system runsc | `D:/xa-evidence/remote/ubuntu-test/` | sealed tarball SHA PASS | system Docker + runsc PASS；rootless + runsc 为 LIMIT |
| R9 本地审计 | `D:/xa-evidence/runs/l3-r9-audit-20260708T075534Z-local/` | 10/10 hashes；3 SM3 records、SM2 signatures、anchor PASS | 本地软件 key/TSA demo；第三方 TSA/HSM 未配置，整体 LIMIT |

R9 目录含 demo 私钥，**不得直接上传或作为公开补充包**。R7 的 Trivy cache 约 1.1 GB，不进入提交包；只取 hash-bound 报告和摘要。

## 6. 完整位置分类

| 类别 | 位置 | 处理 |
|---|---|---|
| canonical sealed | `D:/xa-evidence/runs/`、`D:/xa-evidence/sealed/` | 主证据与本地验收；以 git provenance 为信任锚 |
| remote mirror | `D:/xa-evidence/remote/ubuntu-test/` | R6 完整远端镜像，不复制进 Git |
| current committed evidence | `docs/evidence/`、`docs/acceptance/r8-aibom-external/evidence/` | 可公开附录；保持字节 hash 稳定 |
| legacy local evidence | `D:/evidence/` | R7 可引用；旧 L3/R2/R3 仅库存，不作主结论 |
| generated OAR source | `open-agent-range/.runtime/delivery-v2-canonical-20260711T123009Z/` | sealed 包的源目录；完整副本已进入 canonical run |
| historical OAR/runtime | `open-agent-range/.runtime/` 其他目录 | 回归/研发痕迹，不再作为 canonical |
| legacy range | `enterprise-agent-range/reports/` | 支撑/历史，不作为当前产品主叙事 |
| generated logs | `logs/`、`scripts/.log/` | 当前验证输出；不等于 sealed 验收包 |

`D:/evidence/r2-r3-*` 包含 smoke、calibration、partial jobs 和多次 direct 尝试，未形成统一 sealed final report；Delivery v2 已将其从硬承诺退役，不汇总成 ASR 达标数字。

## 7. 本轮验证账

| 检查 | 结果 |
|---|---|
| OAR full-day replay | PASS，15 hashes、43 ledger、41 audit/tool events |
| OAR live A/B replay | PASS，6/6 sides；XA-Guard 3/3 raw audit alignment |
| canonical standard run | PASS，119 listed files、0 problems |
| canonical tarball | PASS，SHA matches provenance |
| R6 sealed tarballs | PASS，2/2 SHA matches provenance |
| R4 manifest | PASS，8/8 |
| R7 manifest | PASS，20/20 |
| R8 manifest | PASS，7/7；已修复 Git EOL 字节漂移 |
| R9 manifest + audit | PASS，10/10；3 records/SM2/anchor verified |
| 产品 Ruff | PASS；检查 `src/bench/demo/scripts/tools` 与两个 range 产品目录，排除测试目录 |
| pytest | 782 collected；781 passed、1 allowed skip（Windows directory symlink capability）；0 failure/error |
| D2 unified verifier | 2026-07-21 PASS：clean 隔离 Python 环境 `pip check`、产品 Ruff、pytest、L3 static、Compose config、Console 5/5 + build、最终 Identity + Undo evidence verifier |
| L3 static verifier | PASS，11/11 sections；其 runtime-required 列表是工程参考，不覆盖 Delivery v2 状态 |
| Identity + Undo fault suite | PASS，11/11；Worker takeover、retry、wrong KEK、rewrap 均通过 |
| Identity + Undo performance | PASS；完整重建组三轮 p95/upper 45.109/46.984、42.141/43.120、43.934/45.528ms；Undo 10/10 约 0.45–0.94s |
| Kind HA | PASS；N-1→N、migration、API/Worker 接管、NetworkPolicy、rollback |
| Identity + Undo manifest | PASS；14 artifacts、46 Effect、25 Gate6、SM2-with-SM3 key id `87ca0b5c56dc9313` |

## 8. 提交包取舍

建议公开补充证据包只包含：

- canonical OAR sealed tarball及其 manifest 记录；
- R4 的 README、报告和 artifact manifest；
- R7 的 final summary、acceptance report、Trivy report和 artifact manifest，不带 Trivy cache；
- R8 仓内完整 evidence；
- R6 两个 sealed tarball（如附件容量允许）；
- 一份去私钥的 R9 审计样例，重新生成独立公开包后再附。

禁止包含：API token、SSH 密码、R9 `.key`、D4 个人信息、无关 runtime 日志、Trivy cache、未审计的旧 R2/R3 workspace。

## 9. 剩余收尾

1. 优化 Identity + Undo 并发写路径，使正式三轮 incremental p95 和 bootstrap upper 均 ≤50ms。
2. 性能达标后重跑、重封存并独立验证 Identity + Undo evidence。
3. 在干净 commit 上生成 release hash manifest；当前 dirty 状态不能宣称 final release freeze。
4. D4 与三账号 UI 已由负责人确认完成；D1 PDF、D3 视频按要求暂缓，恢复后仍需人工检查页数、时长、隐私和链接。
