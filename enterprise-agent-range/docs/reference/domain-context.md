# 企业域参考

靶场模拟数字城市科技集团，包含办公、运维、业务数据、研发供应链、治理审计等域。数据必须 synthetic，格式像真实业务但不可用于真实系统。

## 主要域

| 域 | 典型资产 | 典型风险 |
|---|---|---|
| Office | 邮件、通知、会议纪要、审批 | 间接注入、误发敏感内容、BEC |
| Operations | 主机、日志、变更、服务状态 | 日志注入、越权重启、危险命令 |
| Business Data | 项目、合同、客户、预算 | 跨域查询、敏感外发 |
| Dev Supply | 插件、AIBOM、CI、制品 | hash mismatch、声明漂移、恶意脚本 |
| Governance | Agent 身份、授权、委托链 | 身份混淆、权限传递 |
| Audit | trace、审计、hash、报告 | 篡改、不可重放、解释不忠实 |

## 数据分级

PUBLIC、INTERNAL、CONFIDENTIAL、SECRET。SECRET 只允许不可用样本；如果 SECRET 出现在 agent 工具入参中，本身就是配置缺陷。