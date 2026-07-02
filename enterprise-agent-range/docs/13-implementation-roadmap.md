# 实施路线

## P0：重型可演示靶场

目标：形成独立、可演示、可复现的最小重型企业靶场。

### P0.1 文档冻结

完成标准：

1. 设计说明完成。
2. 架构完成。
3. 数据模型完成。
4. 数据流完成。
5. 场景矩阵完成。
6. 指标和证据规范完成。
7. 解耦契约完成。

### P0.2 Runtime 骨架

建议新增：

```text
enterprise-agent-range/range_src/enterprise_agent_range/
```

骨架模块：

| 模块 | 职责 |
|---|---|
| `models` | 数据结构。 |
| `fixtures` | fixture 加载。 |
| `systems` | mock 业务系统。 |
| `tools` | MCP-like tools。 |
| `adapters` | SUT adapter。 |
| `runner` | case runner。 |
| `oracles` | oracle engine。 |
| `reports` | 报告生成。 |

### P0.3 Mock 系统

实现：

1. Mail sink。
2. Notification sink。
3. Ops console。
4. Business record API。
5. RAG knowledge base。
6. Plugin registry。
7. Audit store。

### P0.4 Case 与 Fixture

实现：

1. 30+ attack case。
2. 30+ benign control。
3. 10 assurance check。
4. 3+ 多步攻击链。
5. 供应链、审批、审计篡改、冒充高管付款（BEC）链路及其 fixture。

### P0.5 报告

输出：

1. `case-results.jsonl`
2. `side-effects.jsonl`
3. `audit-records.jsonl`
4. `metrics.json`
5. `report.md`
6. `artifact-hashes.json`

## P1：企业完整靶场

目标：支持长期红队和回归。

工作：

1. 扩展 100+ attack case。
2. 扩展 100+ benign control。
3. 支持多 Agent 委托链。
4. 支持 MCP stdio / HTTP。
5. 支持插件包隔离安装。
6. 支持沙箱探针。
7. 支持 mutation engine。
8. 支持 HTML 报告和对比报告。

## P2：研究级靶场

目标：做成智能体安全评测平台。

工作：

1. 多租户。
2. Shadow AI 发现模拟。
3. Agent 身份生命周期。
4. JIT 权限。
5. 风险金额量化。
6. Undo/补偿动作。
7. 攻防演练大屏。
8. 外部 benchmark 融合。
9. 第三方 TSA/HSM 证据接口。

## 优先级建议

第一轮实现顺序：

1. 数据模型和 schema。
2. fixture loader。
3. side-effect sinks。
4. null adapter。
5. oracle engine。
6. 10 个 smoke case。
7. SUT adapter。
8. 完整 P0 case。
9. 报告。

## 解耦检查点

每个阶段完成后检查：

1. 没有 `import xa_guard`。
2. 没有文件写入根 `src/`。
3. 没有新增文件写入既有 `docs/`。
4. case 期望不引用 XA-Guard 内部 rule id。
5. SUT 失败不会导致靶场自身崩溃。
