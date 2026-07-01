# D1 技术方案报告草稿

> 目标：最终导出为 30 页以内 PDF。
> 写作原则：只写已有证据能支撑的结果；未跑完的真实环境和外部依赖写成限制或后续工作。
> 最高依据：[../source-of-truth/XA-202620中国雄安集团数字城市科技有限公司-面向政企场景的大模型智能体安全关键技术研究比赛方案.pdf](../source-of-truth/XA-202620中国雄安集团数字城市科技有限公司-面向政企场景的大模型智能体安全关键技术研究比赛方案.pdf)

## 1. 摘要

- 项目一句话：XA-Guard 是面向政企智能体的 Agent Gateway 和双面 MCP 安全代理。
- 覆盖方向：输入攻击识别、工具执行约束、供应链安全、评测审计溯源。
- 当前结论：核心原型与 L3 静态实现具备，最终真实验收仍有阻塞项。

## 2. 问题分析

- 多源输入攻击：提示注入、RAG 投毒、间接注入、工具输出污染。
- 工具调用风险：越权、敏感数据外发、高危操作无人审批。
- 插件/Skill 供应链风险：恶意包、篡改、能力声明缺失。
- 政企验收风险：审计不可回放、责任归属不清、证据链不可信。

## 3. 总体架构

- XA-Guard MCP Server：对 IDE/智能体暴露安全代理。
- XA-Guard MCP Client：连接真实下游工具。
- 六关卡：Gate1 输入、Gate2 审批、Gate3 策略、Gate4 污点、Gate5 沙箱、Gate6 审计。
- Agent Governance v1：员工、Agent、数据域、预算和审批的本地治理预检。

## 4. 关键技术一：复杂输入链路攻击识别

- 已有：规则检测、Spotlighting、模型后端接入、holdout 协议。
- 可写证据：以 [../gates/gate1-real-model-verification.md](../gates/gate1-real-model-verification.md) 和 [../gates/gate1-holdout-protocol.md](../gates/gate1-holdout-protocol.md) 为准。
- 边界：正式独立 holdout 未完成时，不写正式 Recall/FPR 达标。

## 5. 关键技术二：工具调用与任务执行安全

- 已有：Gate2 风险分级、HITL/pending、Gate3 policy、Gate4 taint、Gate5 沙箱配置。
- 可写证据：L3 静态 verifier、MCP e2e、审计日志、pending ledger。
- 边界：真实 Trae GUI 和 Linux gVisor/runsc 仍按 `BLOCKED` 写。

## 6. 关键技术三：插件与供应链安全

- 已有：内部 AIBOM gateway、离线准入、hash/provenance、CycloneDX-like 导出。
- 可写证据：[../acceptance/L3-aibom-external-generator.md](../acceptance/L3-aibom-external-generator.md) 和 evidence 样例。
- 边界：未接合法外部生成器前，只写“内部 AIBOM 准入原型”。

## 7. 关键技术四：评测、审计与持续优化

- 已有：XA-Bench、CSAB-Gov-mini、AgentDojo/InjecAgent adapter、预算型 runner、Gate6 审计链。
- 可写证据：性能报告、审计验链、R2/R3 dry-run/真实 sampled 结果。
- 边界：`subscription_budget60_v1` 未实跑前，不写 sampled 指标达标。

## 8. 实验设计和结果

表格占位：

| 实验 | 当前状态 | 可写结论 | 证据 |
|---|---|---|---|
| L3 static verifier | `DONE` | 静态实现通过 | status / evidence |
| 全仓 pytest | `DONE/PARTIAL` | 正确环境下通过；sandbox 镜像缺失 skip | status |
| R2/R3 sampled | `TODO/BLOCKED` | 仅工具和 dry-run 准备 | acceptance |
| 性能 | `DONE/PARTIAL` | 历史性能达中等档，最终前建议复跑 | evidence |

## 9. 政企落地价值

- 私有化部署：MCP 代理、Docker Compose、策略 overlay。
- 合规对齐：等保、GB/T 45654、国密审计、OpenTelemetry GenAI 字段。
- 责任归属：human principal、agent id、data domain、task id、approval token、audit hash。

## 10. 当前限制与未来工作

- R1 独立 holdout。
- R2/R3 `$60` sampled 实跑。
- 真实 Trae GUI。
- Linux gVisor/runsc。
- 外部 AIBOM 生成器。
- 第三方 TSA/HSM。
- 生产级 IAM/SSO/RBAC。

## 11. 红线检查

- 不写未验证达标数字。
- 不暴露 token、key、个人隐私。
- 不把本地 demo 写成第三方生产服务。
- PDF 最终页数不超过 30 页。
