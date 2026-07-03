# 解耦契约

## 最高约束

Enterprise Agent Range 必须与 XA-Guard 主产品严格解耦。靶场可以测试 XA-Guard，但不能依赖 XA-Guard 内部实现。

## 目录边界

允许：

- `enterprise-agent-range/README.md`
- `enterprise-agent-range/status.md`
- `enterprise-agent-range/.log/`
- `enterprise-agent-range/docs/`（含 `docs/superpowers/{specs,plans,spikes,handoff}/`，brainstorming/writing-plans 工作流产出的设计与交接文档）
- `enterprise-agent-range/range_src/`（已存在，含 P0/P1/P2 静态回放 runtime 与 `arena/` 解耦平台核心+Live 竖切）
- `enterprise-agent-range/cases/`（含 `cases/arena/` 解耦 Challenge 题目）
- `enterprise-agent-range/fixtures/`（含 `fixtures/arena/` 注入用 fixture）
- `enterprise-agent-range/reports/`（P0/P1 回归证据包与 `reports/arena-live-*` Live 证据）
- `enterprise-agent-range/tests/`
- 后续 `enterprise-agent-range/runtime/`

禁止：

- 把靶场 runtime 放入根 `src/`。
- 把靶场代码放入 `src/xa_guard/`。
- 把靶场文档放入既有根 `docs/`。
- 修改 XA-Guard 现有策略来适配靶场 case。
- 修改 XA-Guard 测试来让靶场通过。

## 代码依赖边界

后续实现时：

| 行为 | 是否允许 | 说明 |
|---|---|---|
| `import xa_guard` | 禁止 | 违反产品解耦。 |
| 调用 XA-Guard CLI | 允许 | 只能作为外部进程 `SUT`。 |
| 通过 HTTP 调用 XA-Guard | 允许 | 与调用其他 SUT 相同。 |
| 读取 XA-Guard 审计日志 | 条件允许 | 必须作为外部证据输入，不依赖内部类型。 |
| 复用 XA-Guard test helper | 禁止 | 会造成测试耦合。 |
| 复用 XA-Guard policy YAML | 禁止 | 靶场应定义自己的期望，不继承被测系统策略。 |
| 复用 XA-Guard docs | 禁止 | 可在报告中引用 SUT 名称，但靶场 docs 自成体系。 |

## SUT Adapter 原则

靶场与 SUT 的交互只通过标准边界：

1. 命令行进程。
2. HTTP API。
3. MCP stdio / HTTP 协议。
4. 文件型证据输入输出。
5. 明确声明的环境变量。

SUT adapter 必须是薄适配层，不允许引用 SUT 内部类、函数、fixture、测试 helper 或私有配置。

`arena/live.py` 是这一原则的落地范例：guard 模式只生成一份临时 YAML，再以外部进程启动 `python -m xa_guard.server --config <生成的yaml>`；null 模式让 OpenCode 直连靶场自己的 `arena/mcp_office_server.py`。两种模式全程不 `import xa_guard`，只通过 stdio MCP 协议 + 事后读取 XA-Guard 落盘的 `audit/audit.jsonl` 作为外部证据输入。这就是"拓扑 A｜双面 MCP 直插"（详见 [05-architecture.md](05-architecture.md) 与 `docs/superpowers/specs/2026-07-02-enterprise-range-decoupling-design.md`）。

## 环境↔题库解耦轴（第二条解耦约束）

上面几节约束的是"靶场↔XA-Guard"这一条轴：靶场不得依赖 SUT 内部实现。**2026-07-02 起新增第二条独立的解耦轴：靶场自身的"企业环境"↔"题库/题目"也必须解耦**，不能因为第一条轴满足了就默认第二条也满足。

背景：早期 P0/P1 case 把 principal/agent（环境）、task（题目）、fixture_refs（题目）和 `execution.steps`（**结果**）全部内联在同一个 case 对象里，且 `execution.steps` 直接写死了工具调用序列——这等于题目作者替 SUT 做了决策，Null Adapter 只是回放脚本，不是真实决策链路。诊断记录见 `docs/superpowers/specs/2026-07-02-enterprise-range-decoupling-design.md` §1。

**约束（适用于新增的 `arena/` 解耦平台，及以后任何号称"解耦"的 case 语料）：**

| 行为 | 是否允许 | 说明 |
|---|---|---|
| Challenge 内联/覆盖 execution.steps 来预定结果 | 禁止（间接注入类） | 结果必须由 AgentSeat（Live 真实 agent 或 Replay 确定性替身）在面对被注入的 World 时自行产生，不能由题目作者写死。 |
| World（Environment）跨多个 Challenge 复用 | 必须 | 同一个 `world_id`（如 `office-baseline`）应能被多道题引用；每道题只声明"注入了什么"，不重新声明整个环境。 |
| 攻击题与良性对照共享 world + 中性任务 | 必须 | 两者应仅在 `inject` 字段上不同（见 `cases/arena/OFFICE-INJ-001.attack.json` 与 `.control.json`），证明环境与题目确实解耦。 |
| 直接注入类（用户本人发起的恶意 prompt，如 AT1.x） | 豁免 | 攻击文本本来就该写在 `task.prompt` 里，这类不需要额外解耦。 |
| 旧 P0/P1 `execution.steps` 回放路径 | 保留，不新增 | 作为既有回归基线继续跑，不删除、不强制迁移，但新的解耦 case 一律走 Challenge schema（见 [17-testcase-schema.md](17-testcase-schema.md)）。 |

## 靶场自己的 oracle

靶场 case 的期望行为由靶场定义，不由 XA-Guard policy 反推。

例如：

- `expected_decision: deny`
- `expected_downstream_call_count: 0`
- `expected_data_exposure: false`
- `expected_audit_chain_valid: true`

如果 SUT 输出不同，记录为测评结果，不修改靶场期望去迎合 SUT。

## 日志和状态

靶场内部工作日志写入：

- `enterprise-agent-range/.log/worklog.md`

靶场当前状态写入：

- `enterprise-agent-range/status.md`

根 `log.md` 和根 `status.md` 只记录仓库级事实：新增独立靶场设计区、不改变 XA-Guard 能力和验收状态。
