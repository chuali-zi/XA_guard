# 总体架构

## 架构目标

Enterprise Agent Range 的架构目标是把真实企业场景、红队攻击、防护系统、评测指标和证据链拆成清晰边界，保证靶场本身独立、可扩展、可替换 SUT。

## 总体视图

```text
┌──────────────────────────────────────────────────────────────┐
│                  Enterprise Agent Range                       │
├──────────────────────────────────────────────────────────────┤
│  Enterprise Simulation Layer                                  │
│  - org / users / departments / data domains                   │
│  - office / ops / data / dev / audit business systems         │
├──────────────────────────────────────────────────────────────┤
│  Agent Interaction Layer                                      │
│  - user tasks / agent personas / multi-agent delegation       │
│  - MCP-like tool calls / RAG reads / plugin install intents   │
├──────────────────────────────────────────────────────────────┤
│  Attack Orchestration Layer                                   │
│  - direct injection / indirect pollution / exfil / bypass     │
│  - supply chain / audit tamper / sandbox probes               │
├──────────────────────────────────────────────────────────────┤
│  SUT Adapter Boundary                                         │
│  - no direct import                                           │
│  - CLI / HTTP / MCP / file evidence only                      │
├──────────────────────────────────────────────────────────────┤
│  Evidence and Evaluation Layer                                │
│  - oracle / metrics / downstream effects / audit verification │
│  - JSON report / markdown report / hash manifest              │
└──────────────────────────────────────────────────────────────┘
```

## 逻辑模块

### Enterprise Simulation Layer

负责模拟企业资产和业务系统。

模块包括：

| 模块 | 职责 |
|---|---|
| Org Registry | 员工、部门、角色、上级、状态。 |
| Asset Registry | 数据资产、系统资产、工具资产、插件资产。 |
| Business Systems | 办公、运维、业务数据、研发供应链、审计。 |
| Data Classifier | 标注 PUBLIC / INTERNAL / CONFIDENTIAL / SECRET。 |
| Mock Side Effect Sink | 捕获邮件、通知、HTTP 外发、工单、变更等副作用。 |

### Agent Interaction Layer

负责表达用户如何请求 Agent，以及 Agent 如何访问工具。

模块包括：

| 模块 | 职责 |
|---|---|
| Principal Session | 用户身份、角色、部门、任务上下文。 |
| Agent Persona | Agent 身份、能力、默认工具、风险等级。 |
| Task Builder | 构造自然语言任务、多步任务和业务目标。 |
| Tool Surface | 暴露 MCP-like tools 或协议模拟接口。 |
| Delegation Model | 表达 Agent-to-Agent 委托和责任链。 |

### Attack Orchestration Layer

负责生成和执行攻击链。

模块包括：

| 模块 | 职责 |
|---|---|
| Attack Fixture Loader | 加载恶意文档、邮件、日志、RAG 片段、插件包。 |
| Scenario Runner | 执行单步或多步 scenario。 |
| Mutation Engine | 后续扩展编码、零宽字符、多轮拆分、语言切换。 |
| Negative Control Builder | 为攻击构造合法相邻样例。 |
| Safety Guardrail | 阻止真实外发、真实删除和不可逆副作用。 |

### SUT Adapter Boundary

负责把靶场请求送给外部被测系统。

适配方式：

| Adapter | 说明 |
|---|---|
| Null Adapter | 无防护 baseline，直接执行 mock tools。 |
| CLI Adapter | 通过外部命令调用 SUT。 |
| HTTP Adapter | 通过 HTTP 调用 SUT。 |
| MCP Stdio Adapter | 通过 stdio 模拟 MCP client。 |
| Evidence Adapter | 读取 SUT 输出的 audit / trace / report。 |

所有 adapter 都不能 import SUT 源码。

Null Adapter 之所以能作为无防护基线，前提是 mock tools 本身不做任何安全拦截判断——如果给 mock 工具预置白名单、权限校验等防护逻辑，Null Adapter 就不再"无防护"，ASR 等指标会失真。mock 工具只负责真实还原企业里的脆弱行为并记录副作用，"该不该拦截"完全交给 oracle 和 SUT 判断，见 [01-design-brief.md](01-design-brief.md) 的"Mock 系统不预置防护"原则。

### Evidence and Evaluation Layer

负责验证实际结果。

模块包括：

| 模块 | 职责 |
|---|---|
| Oracle Engine | 对比 expected 与 actual。 |
| Downstream Effect Checker | 检查副作用是否发生。 |
| Data Exposure Checker | 检查敏感字段是否外泄。 |
| Audit Checker | 检查 trace、字段、hash、重放一致性。 |
| Metrics Aggregator | 计算 ASR、FPR、Utility、审计完整性等。 |
| Report Writer | 输出 JSON、Markdown、HTML 和 hash manifest。 |

## 运行模式

### 本地离线模式

所有业务系统、工具和证据 sink 在本地运行，不访问公网。适合开发和演示。

### SUT 对接模式

靶场通过 adapter 调用外部 SUT，收集 SUT 决策和审计记录。适合评测 XA-Guard 或其他系统。

### 红队交互模式

红队手工操作任务、修改污染样本、提交 case，再由 runner 固化为回归资产。

### 回归评测模式

固定 case manifest、SUT 版本、环境和随机种子，批量执行并生成指标。

## 安全边界

靶场所有副作用必须进入模拟 sink：

| 副作用 | 处理方式 |
|---|---|
| 邮件发送 | 写入 local mail sink。 |
| 通知发送 | 写入 local notification sink。 |
| HTTP 外发 | 写入 egress capture sink。 |
| 服务重启 | 更新 mock service state。 |
| 文件删除 | 操作临时目录或 mock filesystem。 |
| 插件安装 | 写入 isolated plugin workspace。 |
| 审计篡改 | 操作复制出来的 evidence fixture。 |

## 后续代码目录建议

如果进入实现，建议目录为：

```text
enterprise-agent-range/
├── range_src/
│   └── enterprise_agent_range/
├── cases/
├── fixtures/
├── runtime/
├── reports/
└── docs/
```

不得使用根 `src/`，不得加入 `src/xa_guard`。
