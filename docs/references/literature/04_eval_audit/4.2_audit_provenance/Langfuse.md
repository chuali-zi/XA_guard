# Langfuse

## 基本信息
- **类型**: 开源 LLM 可观测性平台
- **官方链接**: https://langfuse.com
- **GitHub**: https://github.com/langfuse/langfuse
- **许可证**: MIT (Core) + Commercial (企业版高级功能)

## 这是什么
Langfuse 是目前 GitHub 星标最高(8k+)的开源 LLM 可观测性平台, 由德国柏林一家初创公司维护。它做的事很专一: 帮你把"LLM 应用跑了什么"全程录下来, 然后用界面让你回看、分析、debug。

可以把它理解为"LLM 应用的 Sentry + Datadog 二合一":
- 类似 Sentry 的部分: 抓异常、抓延迟、抓 token 暴增
- 类似 Datadog 的部分: 多维度查询、看板、告警

它支持本地部署(用 Docker Compose 一键起), 也有云端 SaaS 版本。对政企场景很友好 —— 数据可以全部留在内网, 不出公司一步。集成方式简单: 加几行装饰器即可把任意 Python/TS LLM 应用接入。

## 关键能力
1. **完整链路追踪(Trace)**: 一个用户问题 → Agent → LLM → 工具 → 子 LLM → 输出, 全链路可视化
2. **Prompt 管理**: 把 prompt 当代码管理, 支持版本控制、A/B 测试、灰度发布
3. **评估(Evaluation)**: 内置评估管线 —— LLM-as-Judge, 人工标注, 用户反馈, 三种结合
4. **数据集(Dataset)**: 把生产 trace 一键转化为评估数据集, 形成"线上发现问题 → 沉淀数据集 → 改进模型"的闭环
5. **集成生态**: 原生支持 LangChain, LlamaIndex, OpenAI SDK, LiteLLM, Vercel AI SDK 等主流框架

## 与我们项目的关系
**关卡 6(黑匣子审计) + 运营回路**: Langfuse 是关卡 6 的最快落地路径。建议:
1. 自托管部署 Langfuse(Docker Compose 5 分钟起), 作为 6 关卡的统一日志后端
2. 在 LiteLLM 这一层加 Langfuse 装饰器, 自动捕获所有 LLM 调用
3. 把 ASB / HarmBench 测试集导入 Langfuse 的 Evaluation 模块, 跑红队压测
4. 政企场景关键: 本地部署可保数据合规, 不会有"日志泄露给第三方"风险

## 学习建议
1. 上手 demo: https://langfuse.com/docs/get-started (10 分钟跑通)
2. 看 SDK 集成示例: langfuse-python repo 中的 examples/
3. 试用 self-host 部署: 用 docker-compose.yml 在公司服务器上起一份
4. 与 OpenTelemetry GenAI 对比: Langfuse 自有 schema, 但有 OTel 兼容层, 我们项目可以同时用
