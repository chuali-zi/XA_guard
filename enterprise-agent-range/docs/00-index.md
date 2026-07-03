# 文档索引

Enterprise Agent Range 的文档自成体系，不依赖仓库既有 `docs/`。所有设计默认面向独立靶场，XA-Guard 只是可选外部被测对象 `SUT`。

## 必读顺序

1. [设计说明](01-design-brief.md)
2. [目标与范围](02-goals-and-scope.md)
3. [企业场景](03-enterprise-scenario.md)
4. [解耦契约](04-decoupling-contract.md)
5. [总体架构](05-architecture.md)
6. [数据模型](15-data-model.md)
7. [数据流设计](16-data-flows.md)

## 设计文档

| 文件 | 用途 |
|---|---|
| [01-design-brief.md](01-design-brief.md) | 靶场设计稿，一句话定位、设计原则、整体目标。 |
| [02-goals-and-scope.md](02-goals-and-scope.md) | P0/P1/P2 目标和建设范围。 |
| [03-enterprise-scenario.md](03-enterprise-scenario.md) | 企业背景、业务线、组织和真实感要求。 |
| [04-decoupling-contract.md](04-decoupling-contract.md) | 与 XA-Guard 主产品、根 `src/`、既有 `docs/` 的解耦规则。 |
| [05-architecture.md](05-architecture.md) | 靶场总体架构和模块边界。 |
| [06-security-domains-and-assets.md](06-security-domains-and-assets.md) | 安全域、资产、敏感数据、污染样本和靶标资产。 |
| [07-roles-and-permissions.md](07-roles-and-permissions.md) | 人类角色、Agent 身份、权限边界和跨域约束。 |
| [08-tool-and-system-surface.md](08-tool-and-system-surface.md) | MCP tool、业务系统、RAG、插件市场、审计 sink 等接口面。 |
| [09-attack-taxonomy.md](09-attack-taxonomy.md) | 红队攻击分类和能力检测覆盖面。 |
| [10-scenario-matrix.md](10-scenario-matrix.md) | P0 场景矩阵，含攻击、良性样例和 assurance check。 |
| [11-evaluation-oracles-and-metrics.md](11-evaluation-oracles-and-metrics.md) | oracle、指标、分母规则和报告口径。 |
| [12-evidence-and-audit-requirements.md](12-evidence-and-audit-requirements.md) | 证据、审计、复现包、hash 和报告要求。 |
| [13-implementation-roadmap.md](13-implementation-roadmap.md) | P0/P1/P2 实施路线和完成标准。 |
| [14-risk-and-non-goals.md](14-risk-and-non-goals.md) | 风险、非目标和红线。 |
| [15-data-model.md](15-data-model.md) | 核心实体、关系、case schema 和结果 schema。 |
| [16-data-flows.md](16-data-flows.md) | 正常业务、攻击、审批、供应链、审计和评测数据流。 |
| [17-testcase-schema.md](17-testcase-schema.md) | 靶场 case、fixture、evidence 的独立 schema 草案。 |

## 解耦重构主线（2026-07-02 起）

上述 01-17 篇是靶场原始设计文档，其中 **04、05、15、16、17** 已按下述工作流回填更新，标注了"P0/P1 静态回放（历史，仍在跑）"与"arena/ 解耦平台（当前主线）"两条并存路径。这条主线的完整推导过程和交接现状记录在：

| 文件 | 用途 |
|---|---|
| `docs/superpowers/specs/2026-07-02-enterprise-range-decoupling-design.md` | 设计 spec：目标架构（北极星）+ office/mail 竖切设计 + 迁移策略 |
| `docs/superpowers/plans/2026-07-02-office-mail-slice-core.md` | Plan 1 实现计划：确定性核心（World/Challenge/Injection/SUT/AgentSeat/Oracle） |
| `docs/superpowers/spikes/2026-07-02-xaguard-downstream-mcp.md` | Spike 结论：XA-Guard 下游 MCP 拓扑验证 + Live 2×2 证据 |
| `docs/superpowers/handoff/2026-07-02-session-handoff.md` | 会话交接：现状、已验证结论、已知坑、下一步建议顺序 |

## 当前状态

文档已覆盖靶场建设的核心设计面，且已随 `arena/` 解耦平台的竖切验证同步回填。运行时代码位于 `enterprise-agent-range/range_src/`（P0/P1/P2 静态回放 + `arena/` 解耦平台），仍不得放入仓库根 `src/`。
