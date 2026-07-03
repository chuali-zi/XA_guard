# 总体架构

> **2026-07-02 更新**：本篇原描述的分层模型（Enterprise Simulation Layer / Agent Interaction Layer / Attack Orchestration Layer 直接内联在每个 case 里、`execution.steps` 写死结果）已被诊断为**环境与题库耦合**，详见 `docs/superpowers/specs/2026-07-02-enterprise-range-decoupling-design.md` §1。该模型作为 **P0/P1 静态回放路径**继续保留、继续可跑（不删除、不强制迁移），但**新的解耦平台架构见下面"解耦架构（arena/）"一节，新 case 一律走该架构**。

## 架构目标

Enterprise Agent Range 的架构目标是把真实企业场景、红队攻击、防护系统、评测指标和证据链拆成清晰边界，保证靶场本身独立、可扩展、可替换 SUT。

## 解耦架构（arena/，当前主线）

### 目标架构（北极星）

```text
   红队(人) 造注入                 【Agent 座位｜可插拔】
        │                     ┌───────────────────────────┐
        │ 投毒/出题            │ Live:   真 OpenCode(GLM)   │  ← 被攻击方
        ▼                     │ Replay: 脚本 driver(回归)  │
 ┌──────────────┐             └────────────┬──────────────┘
 │  注入/题库层  │                          │ MCP (工具调用)
 │  Injection    │                          ▼
 │  - 往世界投 payload          ┌────────────────────────┐
 │  - 给中性任务                │   XA-Guard  = SUT       │  ← 产品/防守方
 │  - 定 oracle                 │   6 关卡逐次裁决        │
 └──────┬───────┘              └────────────┬───────────┘
        │ seed/inject                       │ MCP (透传放行的调用)
        ▼                                   ▼
 ┌───────────────────────────────────────────────────────┐
 │  环境世界层 World（常驻、有状态）                       │
 │  - bob / 收件箱 / 项目预算 / 业务系统（容器）           │
 │  - mock-tools MCP server（XA-Guard 下游指向这里）       │
 │  - 副作用 sink（外发邮件=egress capture）               │
 └───────────────────────────┬───────────────────────────┘
                             │ 记录
                             ▼
 ┌───────────────────────────────────────────────────────┐
 │  证据/评测层 Oracle                                     │
 │  = mock-tools 侧副作用记录  +  外部读 XA-Guard 审计日志  │
 │  → 判 deny/data_exposure/… → ASR/FPR/证据包             │
 └───────────────────────────────────────────────────────┘
```

**四层职责**（决策权从"出题人写死 steps"交给"真 agent + XA-Guard"，环境常驻，题库只做注入）：

| 层 | 职责 | 代码位置 |
|---|---|---|
| 环境世界 World | 常驻有状态企业（收件箱/项目/外发 sink），可被多题复用 | `range_src/enterprise_agent_range/arena/world.py` |
| 注入/题库 Challenge | 一道题 = `inject + task + oracle`，**无写死 steps** | `arena/challenge.py`、`arena/injection.py`、`cases/arena/*.json` |
| Agent 座位（可插拔） | Live=真 OpenCode（经 MCP）／Replay=确定性替身（`GullibleAgent`） | `arena/agent_seat.py`（Replay）、`arena/live.py`（Live） |
| SUT | Null 透传／GuardStub 确定性拦截（Replay）；真实 XA-Guard 六关卡（Live，外部进程） | `arena/sut.py`（Replay）、`arena/live.py` 生成 XA-Guard YAML 并外部启动（Live） |
| 证据/评测 Oracle | 依据 World 副作用 + SUT 审计判分 | `arena/oracle.py`、`arena/run.py` |

### 已验证的 Live 拓扑（office/mail 竖切）

```text
OpenCode 1.17.12 (真实 LLM agent, glm-5.2)
  ↓ MCP (stdio)
XA-Guard (SUT，外部进程，guard 模式)  ── null 模式下 OpenCode 直连下一跳，跳过 XA-Guard
  ↓ MCP (stdio，透传放行的调用)
enterprise_agent_range.arena.mcp_office_server（靶场自建，read_mail/query_project/send_email）
  ↓ 读写
World（同一个 world 快照，经 world_from_dict()/to_dict() 跨进程传递）
```

靶场全程不 `import xa_guard`：guard 模式只是 `arena/live.py` 生成一份临时 XA-Guard YAML（含 gate3/gate4 overlay），再用外部进程 `python -m xa_guard.server --config <生成的yaml>` 启动；事后从 `<attempt>/audit/audit.jsonl` 读取审计记录作为外部证据。该拓扑的验证过程见 `docs/superpowers/spikes/2026-07-02-xaguard-downstream-mcp.md`；office/mail 攻击题 vs 良性对照的 2×2 实测证据（含 A/B 防护差值）在 `reports/arena-live-2x2-smoke/`。

### 与 P0/P1 静态回放路径的关系

`arena/` 不替换、不删除下面"总体视图"描述的 P0/P1 分层模型与 `NullAdapter`/`execution.steps` 回放路径——两者并存：

- **P0/P1 路径**：`cases/p0_manifest.json`、`cases/p1_manifest.json`，跑 `python -m enterprise_agent_range run`，用于既有 242+ case 的确定性回归，`execution.steps` 是回放脚本而非活的决策。
- **arena/ 路径**：`cases/arena/*.json`，跑 `python -m enterprise_agent_range arena-live`（Live）或直接调用 `arena/run.py` 的 `run_challenge()`（Replay，纯 Python 确定性替身），是解耦平台的当前与未来主线。

新的间接注入类 case 应该写成 `arena/` 的 Challenge schema，而不是继续往 P0/P1 manifest 里加内联 `execution.steps` 的 case。

## 总体视图（P0/P1 静态回放路径，历史架构，仍在跑）

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
| Null Adapter | 无防护 baseline，直接执行 mock tools（P0/P1 回放路径）。 |
| CLI Adapter | 通过外部命令调用 SUT。 |
| HTTP Adapter | 通过 HTTP 调用 SUT。 |
| MCP Stdio Adapter | 通过 stdio 模拟 MCP client。 |
| Evidence Adapter | 读取 SUT 输出的 audit / trace / report。 |
| **arena Replay（NullSUT/GuardStubSUT）** | 解耦平台确定性替身：`NullSUT` 透传、`GuardStubSUT` 规则拦截，供 TDD 与快速回归用（见 `arena/sut.py`）。 |
| **arena Live（真实 XA-Guard，拓扑 A）** | `arena/live.py` 生成临时 YAML，外部启动 `python -m xa_guard.server --config ...`，经 MCP 对接靶场自建 `mcp_office_server`；真实六关卡裁决，事后读 `audit/audit.jsonl` 取证。 |

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

## 代码目录（现状，2026-07-02）

```text
enterprise-agent-range/
├── range_src/
│   └── enterprise_agent_range/
│       ├── adapters.py, runner.py, tools.py, oracles.py, ...   # P0/P1 静态回放路径
│       ├── p2/                                                 # P2 研究级能力子包
│       └── arena/                                               # 解耦平台核心 + Live 竖切
│           ├── world.py         # 环境世界（Message/Project/EgressRecord）
│           ├── challenge.py     # 解耦题库 schema（inject+task+oracle，无 steps）
│           ├── injection.py     # 按题种世界 + 投毒
│           ├── office_tools.py  # 背靠 World 的确定性工具实现
│           ├── sut.py           # NullSUT / GuardStubSUT（Replay 确定性替身）
│           ├── agent_seat.py    # GullibleAgent（Replay 确定性最坏情形 agent 替身）
│           ├── oracle.py        # 依据 World 副作用 + SUT 审计判分
│           ├── run.py           # Replay 编排器
│           ├── mcp_office_server.py  # 真实 stdio MCP server（Live 下游）
│           └── live.py          # Live runner：生成配置、跑 opencode run、收证据
├── cases/
│   ├── p0_manifest.json, p1_manifest.json   # 静态回放 case（保留）
│   └── arena/                                # 解耦 Challenge 题目（attack/control）
├── fixtures/
│   └── arena/office/                         # 注入用 fixture（含投毒会议纪要）
├── reports/
│   ├── run-p0-null-verify/, run-p1-null-verify/  # 静态回放证据
│   └── arena-live-2x2-smoke/                     # Live 2x2 证据（A/B 防护差值）
├── runtime/          # 预留，尚未使用
└── docs/
    └── superpowers/{specs,plans,spikes,handoff}/
```

不得使用根 `src/`，不得加入 `src/xa_guard`。
