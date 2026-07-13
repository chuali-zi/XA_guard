# D3 演示视频脚本

> 目标：最终视频不超过 10 分钟。
> 原则：展示真实链路，未完成项只说限制，不硬演。

## 视频结构

| 时间 | 内容 | 必须展示 |
|---|---|---|
| 0:00-0:30 | 项目定位 | XA-Guard Agent Gateway 一句话和四方向覆盖 |
| 0:30-1:30 | 架构总览 | 双面 MCP 代理、六关卡、审计链 |
| 1:30-2:45 | 输入攻击拦截 | 间接注入样例、Gate1/Gate3 命中、trace_id |
| 2:45-4:00 | 工具调用和数据流 | 敏感数据、污点传播、越权 deny |
| 4:00-5:15 | 人在环路审批 | pending fallback 或支持 elicitation 客户端；Trae 未实测时不说 native |
| 5:15-6:30 | Agent Governance v1 | 员工-Agent-数据域矩阵、工资条越权 deny、HR 审批 |
| 6:30-7:30 | 供应链准入 | AIBOM preflight、高风险插件 deny |
| 7:30-8:30 | 审计回放 | Gate6 timeline、hash chain、verify_audit |
| 8:30-9:30 | OAR 主评测 | canonical N=3：Null 3/3 泄漏、XA-Guard 3/3 拦截、replay/raw audit alignment |
| 9:30-10:00 | 总结 | 政企价值、当前限制、下一步 |

## 录制前清单

- [ ] 确认仓库 clean 或记录 dirty 状态。
- [ ] 准备独立 demo audit 目录，避免混用历史日志。
- [ ] 准备 3 个最小场景：拦截、审批/拒绝、审计回放。
- [ ] 屏幕不出现 API key、OpenCode token、operator token、个人隐私。
- [ ] 所有数字与 D1 草稿、status 保持一致。
- [ ] 使用 [证据收敛总表](../acceptance/EVIDENCE-CONSOLIDATION.md) 的 canonical hash 和边界。

## 旁白口径

- 可以说：核心原型已具备，静态验收和部分真实验证已完成。
- 可以说：Agent Governance v1 已合入主线，但默认关闭。
- 不能说：L3 最终验收已通过。
- 不能说：R2/R3 sampled 已达标，除非真实跑完。
- 不能说：Trae native elicitation 已验证，除非有真实 GUI 证据。
- 不能说：第三方 TSA/HSM 已接入，除非有第三方证据。
- 可以说：本地 canonical N=3 finding 中 `protection_delta=1.0`；必须同时说明这是确定性本地实验，不是公开 benchmark 总体 ASR。

## 输出物

- [ ] 原始录屏文件。
- [ ] 剪辑工程。
- [ ] 最终视频文件。
- [ ] 视频 hash。
- [ ] 使用到的命令和证据路径。
