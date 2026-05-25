# AgentOps

## 基本信息
- **类型**: 商业 + 开源 SDK(可观测性工具)
- **官方链接**: https://www.agentops.ai
- **GitHub**: https://github.com/AgentOps-AI/agentops
- **许可证**: MIT (SDK) + 商业 SaaS

## 这是什么
AgentOps 专注于"Agent"这一类应用(不是单次 LLM 调用), 给多步 Agent 工作流提供观测、回放、调试能力。和 Langfuse / Phoenix 相比, AgentOps 的差异化在于:
1. **会话(Session)中心化**: 一个 Agent 完成一个用户任务称为一个 Session, AgentOps 围绕 Session 组织所有数据
2. **Agent 框架原生集成**: CrewAI, AutoGen, LangGraph, OpenAI Swarm 等主流 Agent 框架都有官方插件
3. **回放与调试**: 可以"录制" Agent 一次完整执行, 然后在 UI 中逐步前进 / 后退 / 修改某步重跑

AgentOps 由 Y Combinator 孵化, 商业模式是 SaaS + 企业自托管。免费版有 Session 数量限制, 付费版无限制 + 高级功能。

## 关键能力
1. **Session 录制与回放**: 一次完整 Agent 执行可"录像", 支持逐步回放
2. **成本与延迟监控**: 每个 Session 的 token 成本、延迟、API 调用次数
3. **多 Agent 编排追踪**: CrewAI / AutoGen 的多个 Agent 协作过程可视化
4. **Eval Engine**: 内置评估管线, 支持自定义评估函数
5. **集成超过 1000+ LLM**: 通过 LiteLLM 等中间件, 覆盖几乎所有 LLM 供应商

## 与我们项目的关系
**关卡 6(黑匣子审计)**: AgentOps 的"Session 回放"能力恰好对应关卡 6 的"重审决策"需求。和 Replayable Financial Agents (2601.15322) 论文的思想异曲同工。建议:
- 在原型阶段用 AgentOps SDK 快速实现"Session 录制 + UI 回放"
- 政企场景如果对"商业 SaaS"有顾虑, 可考虑自托管(企业版支持)
- 与 Langfuse / Phoenix 不是替代关系, AgentOps 更聚焦 Agent 多步执行的"剧本回放", 可以并行使用

## 学习建议
1. 上手: `pip install agentops`, 在代码中调 `agentops.init()` 即可开始记录
2. 看 GitHub examples 目录的多 Agent 协作示例
3. 与 CrewAI / AutoGen 配合使用最能体现价值
4. 自托管: 需要联系销售, 价格较贵, 仅在政企必要时考虑
