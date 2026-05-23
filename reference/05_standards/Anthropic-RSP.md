# Anthropic Responsible Scaling Policy（RSP）

## 基本信息
- **发布机构**: Anthropic（Claude 大模型开发商）
- **首版发布**: 2023 年 9 月
- **最新版本**: 持续更新中（建议查官网）
- **官方链接**: https://www.anthropic.com/news/anthropics-responsible-scaling-policy
- **法律层级**: 企业自律承诺（非强制法律）

## 一句话总结
Anthropic 自己定的"大模型分级管控政策"——按模型危险性分 ASL 等级，越危险约束越严。

## 这是什么

Anthropic 是大模型领域少数主动承诺安全责任的企业。RSP（Responsible Scaling Policy）是他们的**自我约束文件**：

**ASL（AI Safety Levels）分级**：

- **ASL-1**：完全无害（窄任务模型，如下棋 AI）
- **ASL-2**：基本无危险能力（当前主流 LLM 在这里）
- **ASL-3**：开始有显著危险能力（如可显著增强非专家完成 CBRN 攻击）
- **ASL-4**：自主性危险（模型能自主进行 AI 研究）
- **ASL-5**：超越人类能力的全面危险

**核心承诺**：每升级一个 ASL，对应的安全控制必须升级（如红队测试覆盖率、模型权重保护、部署限制等）。如果安全控制达不到，**就不发布**这一代模型。

## 类似政策（业界）

- **OpenAI Preparedness Framework**：类似分级思路
- **Google DeepMind Frontier Safety Framework**：类似分级思路
- **Meta** / **Microsoft** 也有内部类似政策

## 与我们项目的关系

学术对标价值——**RSP 的"分级管控"思路可以借鉴**到我们的政企智能体风险等级评估：

- 我们的智能体可以根据"能调用什么工具"做风险分级
- 不同级别对应不同强度的安全控制（HITL 审批的紧迫度、审计日志详细程度等）

报告价值：「本方案借鉴 Anthropic RSP 的分级管控思路，对智能体能力进行 L1-L4 风险分级」。

## 学习建议

- **优先级**：低（学术 / 业界视野扩展）
- **必看**：官方网页 5 分钟概览
- **关键概念**：ASL 等级与缓解措施的对应关系

## 与本目录其他资源的关系

- 与各国官方标准互补——RSP 是企业层面，官方标准是法规层面
