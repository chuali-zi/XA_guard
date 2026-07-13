# 下一步工作设计

> 快照：**2026-07-11**（对齐 [DELIVERY-v2](../acceptance/DELIVERY-v2.md)）
> 目标：把「接下来做什么」固定为可执行顺序，不与 PRD、TODO、status 打架。
> 状态标签：`DONE` / `PARTIAL` / `TODO` / `RETIRED` / `REFERENCE`
> **比赛交付权威口径**：[DELIVERY-v2](../acceptance/DELIVERY-v2.md) · 仓库状态：[status.md](../../status.md)

## 1. 当前总体结论

仓库不是空壳：XA-Guard 六关卡、MCP 代理、审计、AIBOM、Agent Governance v1 与 **Open Agent Range（OAR）主评测证据**均已具备。

当前只能谨慎写成：

> **Delivery v2**：Tier A（D1/D3/D4）未完成；Tier B 主体 `DONE`，B5 canonical OAR 证据链待冻结；Tier C 为可选附录。

**不再使用**「L3 最终验收 BLOCKED」作为项目主叙事。工程 L3 清单见 [L3-test-and-acceptance.md](../acceptance/L3-test-and-acceptance.md)（已弃用为比赛承诺）。

## 2. Tier A — 官方 D1–D4

| 交付物 | 状态 | 下一步 |
|---|---|---|
| D1 技术方案 PDF | `TODO` | [D1 草稿](../delivery/D1-technical-report-draft.md)，主实验写 OAR A/B |
| D2 原型代码/仓库 | `PARTIAL` | clean main、复现命令、artifact hash |
| D3 演示视频 | `TODO` | [D3 脚本](../delivery/D3-video-script.md)：demo + OAR A/B + 审计回放 |
| D4 审核通过报名表 | `TODO` | 人工确认；仓库不伪造证据 |
| 可选补充材料 | `PARTIAL` | [提交清单](../delivery/submission-checklist.md) |

## 3. 四个赛题方向（Delivery v2 叙事）

| 方向 | 状态 | D1 主证据 |
|---|---|---|
| 1 复杂输入链路攻击识别 | `PARTIAL` | Gate1 demo + CSAB seed；holdout 协议为 `RETIRED` 正式指标 |
| 2 工具调用与任务执行安全 | `DONE/PARTIAL` | Gate2–5 + OAR seat/SUT；Trae/gVisor runsc 为 `RETIRED` 硬承诺 |
| 3 插件/Skill/脚本供应链 | `PARTIAL` | AIBOM 准入 + OAR supply consequence；marketplace hook `RETIRED` |
| 4 评测、审计溯源 | `DONE/PARTIAL` | **OAR A/B + ledger replay**；R2/R3 `$60` 为 Tier C 可选 |

## 4. 工程资产与退役项

| 项 | 比赛口径 | 说明 |
|---|---|---|
| L3 静态 S1–S7 | `REFERENCE` | 工程成熟度证据，非比赛 blocker |
| OAR Tier B | `DONE`（B5 canonical sealed） | 主评测叙事；见证据收敛总表 |
| R2/R3 budget60 | `RETIRED` mandatory | Tier C 后台实验；工具保留 |
| R4/R7/R8 本地证据 | Tier C | 可抄进 D1 附录 |
| R1 holdout / 2986 矩阵 / R9 TSA/HSM / R5 Trae native / R6 runsc 全套 | `RETIRED` | 见 DELIVERY-v2 退役表 |

## 5. P0 执行顺序

1. 确认 D4 报名审核状态。
2. 起草 D1：四方向 + OAR 一节 + 诚实限制（不写退役项为 blocker）。
3. 冻结一条 canonical OAR 证据链（DELIVERY-v2 §B5 命令）并写入 D1/D3。
4. 录制 D3：demo 场景 → OAR Null vs XA-Guard → `verify_audit`。
5. 跑不花钱验证：`pytest`、`demo/scenarios`、OAR replay smoke。
6. 收束 D2：README、提交清单、artifact hash。

## 6. P1 / P2（可选，不欠账）

| 优先级 | 工作 | 口径 |
|---|---|---|
| P1 | Tier C：R4/R7/R8 数字进 D1 附录 | 已有证据即可 |
| P1 | Tier C：Trae 截图 2–4 张 | 非 native elicitation 硬承诺 |
| P2 | R2/R3 服务器后台跑 | 有结果写附录，无结果不写达标 |
| P2 | Agent Governance API / SSO | future work |

## 7. 不可夸大声明清单

- 不写「L3 最终验收通过」或「L3 整体 BLOCKED」作主状态。
- 不把 `protection_delta` 写成 AgentDojo ASR≤10%。
- 不把 `subscription_budget60_v1` 写成比赛 mandatory。
- 不把 2,986-job 矩阵写成必需或已完成。
- 不把 Trae fallback 写成 native elicitation。
- 不把本地 TSA/软件 SM2 写成第三方 TSA/HSM。
- 不把 OAR 说成官方 benchmark 替代品——写清「自建红队靶场指标」。

## 8. 实施者默认口径

- 新数字必须能回到脚本输出、OAR evidence 目录或 `verify_audit`。
- `status.md` = 当前状态；`log.md` = 工作历史（顶层追加）。
- 费用、外部 GUI、生产 key → Tier C 或 `RETIRED`，不标比赛 `BLOCKED`。
