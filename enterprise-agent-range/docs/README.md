# Enterprise Agent Range 文档入口

本目录只保留当前红队靶场建设需要的活文档。旧的编号文档和历史工作流痕迹已清理，避免把历史 brainstorm、handoff、过时 plan 当成当前真相源。

## 先读顺序

1. [红队靶场重构计划 / 当前执行状态](plan/redteam-arena-refactor-plan.md)
2. [Arena Core 架构](architecture/arena-core.md)
3. [解耦契约](architecture/decoupling-contract.md)
4. [红队成员操作指南](redteam/operator-guide.md)
5. [证据与指标口径](architecture/evidence-and-metrics.md)

## 目录结构

```text
docs/
├── README.md
├── plan/            # 待审核和执行的具体重构计划
├── architecture/    # 当前架构、契约、证据口径
├── redteam/         # 红队成员上手和攻关流程
└── reference/       # 域背景、攻击面、历史 smoke 结论、P2 范围
```

## 当前事实

- 主线目标不是先扩展题库，而是把 `arena/` 重构成红队可操作的攻关平台核心；截至 2026-07-02 20:06，Arena Core 第一层和最小 CLI 红队台已实现。
- 旧 P0/P1 manifest 与 `execution.steps` 回放路径继续保留为回归基线，但不再作为新增间接注入 case 的主线。
- 新增或迁移的间接注入题必须走 `World + inject + neutral task + oracle`，不允许写死工具调用结果；finding 草稿通过 `arena init-finding` 创建，经审核后用 `arena promote` 固化为 challenge。
- XA-Guard 只能作为外部 `SUT` 接入：进程、HTTP、MCP 或文件证据；靶场代码不得 `import xa_guard`。当前 `rg "from xa_guard|import xa_guard" enterprise-agent-range/range_src/enterprise_agent_range` 无匹配。
- 旧工作流目录的有用结论已并入本目录的 plan、architecture 和 reference 文档；详细历史可从 git 历史追溯，不再污染当前入口。