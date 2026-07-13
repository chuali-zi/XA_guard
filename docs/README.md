# 项目文档总入口

> 项目：XA-202620 · 面向政企场景的大模型智能体安全关键技术研究
> 文档目录版本：v6（2026-07-12 Identity + Undo 正式接入）
> 最高依据：赛题 PDF > 事实源 > **DELIVERY-v2** > PRD > 架构/工作设计 > 研究资料
> 正式安全能力： [Agent Identity + Undo 架构与上线边界](architecture/agent-identity-and-undo.md)

本目录按用途分区。顶层只保留本入口。

## 30 秒目录树

```text
docs/
├── README.md
├── source-of-truth/     # 赛题原文、事实源
├── planning/            # PRD、产品架构、项目总览
├── workplan/            # TODO、下一步设计
├── delivery/            # D1/D3/提交清单
├── acceptance/          # DELIVERY-v2（权威）、L3（工程参考）、R2-R3 工具说明
├── gates/               # Gate 专题
├── bench-redteam/       # HACK-BENCH、XA-Bench
├── research/            # 答辩研究资料
├── tutorials/
├── references/
└── evidence/            # 版本化证据样例
```

## 下一步先看什么

| 目的 | 入口 | 状态 |
|---|---|---|
| **比赛交什么、欠什么（权威）** | [acceptance/DELIVERY-v2.md](./acceptance/DELIVERY-v2.md) | `ACTIVE` |
| **全部证据、hash 与边界** | [acceptance/EVIDENCE-CONSOLIDATION.md](./acceptance/EVIDENCE-CONSOLIDATION.md) | `DONE` |
| 判断仓库当前状态 | [../status.md](../status.md) | `PARTIAL` |
| 执行优先级与 TODO | [workplan/TODO.md](./workplan/TODO.md) | `TODO` |
| 下一步工作设计 | [workplan/NEXT-WORK-DESIGN.md](./workplan/NEXT-WORK-DESIGN.md) | `REFERENCE` |
| 写 D1 技术方案 | [delivery/D1-technical-report-draft.md](./delivery/D1-technical-report-draft.md) | `TODO` |
| 录 D3 视频 | [delivery/D3-video-script.md](./delivery/D3-video-script.md) | `TODO` |
| 准备提交包 | [delivery/submission-checklist.md](./delivery/submission-checklist.md) | `TODO` |
| L3 工程验收清单（已弃用为比赛承诺） | [acceptance/L3-test-and-acceptance.md](./acceptance/L3-test-and-acceptance.md) | `DEPRECATED` |
| R2/R3 预算 runner（背景/附录） | [acceptance/R2-R3矩阵自动验收使用说明.md](./acceptance/R2-R3矩阵自动验收使用说明.md) | `RETIRED` |
| OAR 主评测 | [../open-agent-range/](../open-agent-range/) | `DONE` |
| Agent Identity + Undo 可行性 | [planning/agent-identity-undo-feasibility.md](./planning/agent-identity-undo-feasibility.md) | `EXPERIMENT GO` |
| Agent Identity + Undo 第二轮 | [planning/agent-identity-undo-feasibility-round2.md](./planning/agent-identity-undo-feasibility-round2.md) | `ROUND2-GO` |

## 状态标签

| 标签 | 含义 |
|---|---|
| `ACTIVE` | 当前权威口径 |
| `DONE` | 已有代码/文档/证据，可在边界内宣称完成 |
| `PARTIAL` | 主体完成，仍缺正式交付或冻结证据 |
| `TODO` | 尚未完成的真实差距 |
| `RETIRED` | 不再作为比赛承诺或 BLOCKED |
| `DEPRECATED` | 保留作工程参考，不作比赛交付依据 |
| `REFERENCE` | 研究/历史依据 |
| `EXPERIMENT GO` | 隔离竖切通过，只证明可行性，不代表正式产品交付 |
| `ROUND2-GO` | 真实传输与持久恢复竖切通过，仍不代表生产化完成 |

## 分区说明

| 目录 | 用途 |
|---|---|
| `source-of-truth/` | [事实源](./source-of-truth/事实源.md)、赛题 PDF |
| `planning/` | PRD、产品架构、项目总览 |
| `workplan/` | [TODO](./workplan/TODO.md)、NEXT-WORK-DESIGN |
| `delivery/` | D1 草稿、D3 脚本、提交清单 |
| `acceptance/` | **DELIVERY-v2**、L3（deprecated）、R2-R3 工具文档 |
| `gates/` | Gate1–4、Trae 静态 |
| `bench-redteam/` | 红队协作规范 |
| `research/` | FORCE 2026 等 |
| `evidence/` | 可引用证据样例 |

## Delivery v2 快照（2026-07-11）

| 项 | 状态 |
|---|---|
| DELIVERY-v2 口径 | `ACTIVE` |
| Tier A D1/D3/D4 | `TODO` |
| Tier A D2 | `PARTIAL` |
| Tier B OAR 主证据 | `DONE`（B5 canonical sealed） |
| Tier C R4/R7/R8 | `DONE` |
| L3 作比赛 BLOCKED 叙事 | `RETIRED` |
| R2/R3 budget60 硬承诺 | `RETIRED` |

## 维护规则

- 交付口径变更：更新 `acceptance/DELIVERY-v2.md`、`../status.md`、`../log.md` 顶条。
- 勿将 DELIVERY-v2 退役项重新标为 BLOCKED。
- 移动文档后修链接并在 `log.md` 记录。

## 根级关联

- [../README.md](../README.md) — 代码快速开始
- [../status.md](../status.md) — 仓库状态（Delivery v2）
- [../log.md](../log.md) — 工作日志
