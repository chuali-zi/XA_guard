# 解耦契约

## 最高约束

Enterprise Agent Range 是独立靶场。它可以评测 XA-Guard，但不能依赖 XA-Guard 内部实现。

## 允许边界

| 行为 | 状态 |
|---|---|
| 通过命令行启动外部 SUT | 允许 |
| 通过 HTTP / MCP stdio / MCP HTTP 调用外部 SUT | 允许 |
| 读取外部 SUT 落盘审计作为证据 | 允许 |
| 把 XA-Guard 当成 `sut_mode=guard` | 允许 |
| `import xa_guard` 或复用 XA-Guard helper | 禁止 |
| 修改 XA-Guard 策略来迎合靶场 | 禁止 |
| 把靶场 runtime 放到根 `src/` | 禁止 |
| 新增间接注入 case 时写死 `execution.steps` | 禁止 |

## 环境与题库解耦

新增 arena case 必须遵守：

- World 是环境，可被多个 challenge 复用。
- Challenge 只声明 inject、task、oracle。
- 间接注入类攻击不能预置工具调用序列。
- 攻击题和良性对照应尽量共享 world 与中性 task，只切换 inject。
- 旧 P0/P1 `execution.steps` 路径保留为回归基线，不作为新增主线。

## Mock 系统原则

Mock 工具不预置安全拦截。它们只执行合成业务动作并记录本地副作用。是否应该 allow/deny 由 SUT 和 oracle 共同验证；否则 Null baseline 会被虚假加固。