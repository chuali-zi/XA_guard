# 项目文档总入口

> 项目：XA-202620 · 面向政企场景的大模型智能体安全关键技术研究
> 文档目录版本：v4（2026-06-30 docs 物理重构后）
> 最高依据：赛题 PDF > 事实源 > PRD > 架构/验收/工作设计 > 研究资料

本目录现在按用途分区。顶层只保留本入口，避免 PRD、验收、研究、证据和下一步 TODO 混在一起。

## 30 秒目录树

```text
docs/
├── README.md
├── source-of-truth/     # 赛题原文、事实源和纠偏口径
├── planning/            # PRD、产品架构、项目总览
├── workplan/            # 当前 TODO 和下一步工作设计
├── delivery/            # D1/D3/提交清单工作区
├── acceptance/          # L2/L3/R2-R3/Trae/AIBOM/外部评测验收说明
├── gates/               # Gate1、Gate2/3/4、规则样例、风险分级专题
├── bench-redteam/       # HACK-BENCH 与 XA-Bench 协作规范
├── research/            # 答辩和产品叙事研究资料
├── tutorials/           # 上手教程
├── references/          # 文献、调研、历史归档
├── evidence/            # 已版本化证据样例
└── .log/                # docs 子目录工作日志
```

## 下一步先看什么

| 目的 | 入口 | 状态 |
|---|---|---|
| 判断现在到底做完什么 | [../status.md](../status.md) | `PARTIAL` |
| 看接下来怎么推进 | [workplan/NEXT-WORK-DESIGN.md](./workplan/NEXT-WORK-DESIGN.md) | `TODO` |
| 看详细 TODO 和交付收束 | [workplan/TODO.md](./workplan/TODO.md) | `TODO` |
| 写 D1 技术方案 | [delivery/D1-technical-report-draft.md](./delivery/D1-technical-report-draft.md) | `TODO` |
| 录 D3 视频 | [delivery/D3-video-script.md](./delivery/D3-video-script.md) | `TODO` |
| 准备最终提交包 | [delivery/submission-checklist.md](./delivery/submission-checklist.md) | `TODO` |
| 跑 L3/R1-R9 验收 | [acceptance/L3-test-and-acceptance.md](./acceptance/L3-test-and-acceptance.md) | `PARTIAL/BLOCKED` |
| 跑 R2/R3 预算评测 | [acceptance/R2-R3矩阵自动验收使用说明.md](./acceptance/R2-R3矩阵自动验收使用说明.md) | `TODO/BLOCKED` |
| 接手 R8 外部 AIBOM | [acceptance/r8-aibom-external/README.md](./acceptance/r8-aibom-external/README.md) | `DONE/PARTIAL` |

## 状态标签

| 标签 | 含义 |
|---|---|
| `DONE` | 已有代码/文档/测试或证据支撑，可在边界内宣称完成 |
| `PARTIAL` | 主体完成，但仍缺正式证据、真实环境或外部条件 |
| `BLOCKED` | 需要人工、外部环境、第三方服务或真实客户端，当前仓库无法单独完成 |
| `TODO` | 尚未开始或只有设计/骨架 |
| `REFERENCE` | 研究、标准、会议资料或历史依据，不直接等同当前实现 |
| `ARCHIVE` | 历史版本或分发物，只用于追溯 |

## 分区说明

| 目录 | 用途 | 核心文件 |
|---|---|---|
| `source-of-truth/` | 权威事实、赛题原文、纠偏口径 | [事实源.md](./source-of-truth/事实源.md)、赛题 PDF |
| `planning/` | 产品与技术设计 | [PRD.md](./planning/PRD.md)、[产品架构.md](./planning/产品架构.md)、[项目总览.md](./planning/项目总览.md) |
| `workplan/` | 当前状态分析、下一步执行顺序 | [NEXT-WORK-DESIGN.md](./workplan/NEXT-WORK-DESIGN.md)、[TODO.md](./workplan/TODO.md) |
| `delivery/` | 比赛交付物工作区 | D1 草稿、D3 视频脚本、提交清单 |
| `acceptance/` | 验收、复现、外部评测和证据规范 | L2/L3、R2/R3、Trae、AIBOM、external benchmarks |
| `gates/` | Gate 级专题和策略审核 | Gate1、Gate2/3/4、风险分级、规则样例 |
| `bench-redteam/` | 红队和 bench 维护协作规范 | HACK-BENCH、XA-Bench |
| `research/` | 答辩叙事、会议笔记和研究沉淀 | FORCE 2026 专题 |
| `tutorials/` | 手把手教程 | MCP 入门、HITL toy probe |
| `references/` | 文献库、产品形态调研、历史归档 | literature、product-forms、archive |
| `evidence/` | 可提交的样例证据和历史测试输出 | L3 性能、审计、外部 benchmark smoke |

## 当前已完成和未完成

| 项 | 状态 | 说明 |
|---|---|---|
| docs 分类存储 | `DONE` | 顶层文档已按职责进入子目录 |
| Agent Governance v1 | `DONE` | 已合入 main；默认关闭；不是生产 IAM/SSO |
| L3 静态实现验收 | `DONE` | 静态 verifier 历史记录为 PASS；最终 L3 仍非 PASS |
| D2 代码原型 | `PARTIAL` | 核心代码和 README 具备，仍需 release freeze 和最终证据包 |
| R2/R3 `$60` sampled 实跑 | `TODO/BLOCKED` | 工具已具备，正式付费校准和 sampled 结果未完成 |
| 真实 Trae GUI | `BLOCKED` | 静态模板有，真实 GUI 证据未补 |
| Linux gVisor/runsc | `BLOCKED` | Windows 本机缺 runsc runtime |
| 外部 AIBOM 生成器 | `BLOCKED` | 内部 AIBOM 有，合法外部生成器证据未补 |
| 第三方 TSA/HSM | `BLOCKED` | 本地 TSA/软件 SM2 key 不能冒充第三方 |
| D1 PDF / D3 视频 / D4 报名材料 | `TODO` | 仓库未发现最终交付成品 |

## 维护规则

- 新增正式交付相关文档放 `delivery/` 或 `workplan/`。
- 新增验收或复现说明放 `acceptance/`。
- 新增 Gate 级策略、模型、风险说明放 `gates/`。
- 新增研究资料放 `research/` 或 `references/`，不要写成当前实现。
- 移动文档后必须修相对链接，并在 [../log.md](../log.md) 顶部记录。
- 仓库能力或验收边界变化时，更新 [../status.md](../status.md)。

## 根级关联文件

- [../README.md](../README.md)：代码和快速开始入口
- [../status.md](../status.md)：当前仓库状态、能力边界、BLOCKED 清单
- [../log.md](../log.md)：客观工作日志
