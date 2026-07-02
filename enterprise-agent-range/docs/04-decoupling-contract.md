# 解耦契约

## 最高约束

Enterprise Agent Range 必须与 XA-Guard 主产品严格解耦。靶场可以测试 XA-Guard，但不能依赖 XA-Guard 内部实现。

## 目录边界

允许：

- `enterprise-agent-range/README.md`
- `enterprise-agent-range/status.md`
- `enterprise-agent-range/.log/`
- `enterprise-agent-range/docs/`
- 后续 `enterprise-agent-range/range_src/`
- 后续 `enterprise-agent-range/cases/`
- 后续 `enterprise-agent-range/fixtures/`
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
