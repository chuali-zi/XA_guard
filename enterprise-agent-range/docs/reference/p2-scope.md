# P2 能力范围参考

P2 是研究级能力子包，不是当前红队台第一优先级。当前 P2 模块已经有确定性 stdlib 实现和单测，但未接入 runner/oracle/metrics/report 的正式分母。

## 能力清单

| 编号 | capability | 说明 |
|---|---|---|
| P2-1 | tenancy | 多租户企业 |
| P2-2 | discovery | Shadow AI 发现模拟 |
| P2-3 | identity | Agent 身份生命周期 |
| P2-4 | permissions | JIT/JEA/JLA 权限签发 |
| P2-5 | risk | 风险金额量化 |
| P2-6 | remediation | Undo / 补偿动作建议 |
| P2-7 | scale | 大规模自动化 runner |
| P2-8 | benchmark | 外部 benchmark 融合 |
| P2-9 | evidence | 第三方 TSA/HSM 证据接口 |
| P2-10 | dashboard | 攻防演练大屏和复盘报告 |

## 当前边界

- 不影响 P0/P1 runner。
- 不接真实 HSM/TSA。
- 不接真实外部 benchmark。
- 不应阻塞 arena core 和红队工作台重构。