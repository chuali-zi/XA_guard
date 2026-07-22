# 最终提交清单

> 目标：提交前一张表看清楚 D1-D4、补充材料、证据 hash、红线检查。
> **交付口径**：[../acceptance/DELIVERY-v2.md](../acceptance/DELIVERY-v2.md)
> 官方赛题依据：[../source-of-truth/XA-202620中国雄安集团数字城市科技有限公司-面向政企场景的大模型智能体安全关键技术研究比赛方案.pdf](../source-of-truth/XA-202620中国雄安集团数字城市科技有限公司-面向政企场景的大模型智能体安全关键技术研究比赛方案.pdf)

## D1-D4（Tier A）

| 交付物 | 状态 | 文件/链接 | 负责人确认 |
|---|---|---|---|
| D1 技术方案 PDF，不超过 30 页 | `DONE` | `output/pdf/XA-Guard-XA-202620-technical-report.pdf`（14 页） | [x] |
| D2 原型代码仓库链接 | `PARTIAL` | GitHub main + release commit | [ ] |
| D3 演示视频，不超过 10 分钟 | `MANUAL-PENDING` | 逐镜指南与字幕模板完成；待负责人录制/导出 | [ ] |
| D4 审核通过报名表 | `DONE` | 2026-07-18 负责人确认；隐私材料在仓库外 | [x] |

## 证据包（Tier B 为主）

权威清单、hash 和发布取舍见 [证据收敛总表](../acceptance/EVIDENCE-CONSOLIDATION.md)。

- [ ] final commit hash。
- [ ] `git status --short` 干净截图或文本。
- [x] 统一自动验证输出（2026-07-18：772 collected，771 passed、1 Windows directory-symlink capability skip；产品 Ruff、L3 static、Compose、Console、证据验签均通过）；提交前在 final commit 再跑一次并固定 hash。
- [x] L3 static verifier 输出（工程参考，11/11 sections PASS）。
- [x] **OAR canonical 证据目录**：`oar-delivery-v2-20260711T123124Z-win-local`。
- [x] OAR live A/B summary：N=3、`protection_delta=1.0`、7/7 replay PASS。
- [x] 六关 demo/audit 证据入口与本地 SM3/SM2 校验。
- [x] 性能报告（Tier C 附录，可选）。
- [x] R8 cdxgen / install_plugin 证据（Tier C 附录，可选）。
- [ ] R2/R3 sampled：仅当背景实验已跑时附；否则标 `RETIRED` / 省略。
- [x] OAR sealed provenance 与 Identity + Undo 签名 evidence manifest。
- [ ] D2 最终 release manifest：仅在 clean final commit 上运行 `python scripts/build_release_manifest.py` 后勾选。

## 邮件与附件

- [ ] 邮件主题按官方或咨询确认格式填写。
- [ ] 正文写明题号 XA-202620 和题目全称。
- [ ] 附 D1 PDF。
- [ ] 附 D2 仓库链接和复现说明。
- [ ] 附 D3 视频或网盘链接。
- [ ] 附 D4 审核通过报名表。
- [ ] 附补充证据包链接。
- [ ] 网盘链接有效期覆盖初审/决赛窗口。
- [ ] 保存已发送邮件、回执和网盘访问截图。

## 红线检查

- [x] PDF 不超过 30 页（14 页）。
- [ ] 视频不超过 10 分钟。
- [ ] 不暴露 API key、token、私钥、账号。
- [ ] 不暴露无关个人隐私。
- [ ] 所有达标数字都有证据来源。
- [ ] 未完成项写限制或 future work；**退役项**（见 DELIVERY-v2）不写成 blocker。
- [ ] 本地 TSA/软件 key 不写成第三方 TSA/HSM。
- [ ] 主评测叙事为 OAR A/B，不把 AgentDojo ASR 或 budget60 写成 mandatory 达标。
