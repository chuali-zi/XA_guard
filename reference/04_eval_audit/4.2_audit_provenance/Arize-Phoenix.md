# Arize Phoenix

## 基本信息
- **类型**: 开源 LLM 可观测性平台
- **官方链接**: https://phoenix.arize.com
- **GitHub**: https://github.com/Arize-ai/phoenix
- **许可证**: Elastic License v2(可商用, 不可作为 SaaS 转售)

## 这是什么
Phoenix 是 Arize AI(美国湾区 MLOps 公司)开源的 LLM 可观测性工具。和 Langfuse 同属一个赛道, 但定位略有差异: Phoenix 更偏"模型评估和数据科学家工作流", Langfuse 更偏"应用开发和产品迭代"。

Phoenix 的母公司 Arize 本来做的是传统 ML 模型监控(模型漂移、数据漂移检测), LLM 时代他们把这套能力迁移过来, 所以 Phoenix 在"嵌入向量空间可视化"、"模型评估指标"这块特别强。可以在本地 Jupyter Notebook 一行起服务, 也可以独立部署。

国际上 Phoenix 用户群体偏研究和评估, Langfuse 偏生产应用 —— 但两者功能重叠 80%, 选哪个看团队偏好。

## 关键能力
1. **OpenTelemetry 原生**: Phoenix 基于 OTel GenAI 规范, 直接消费标准 OTel trace
2. **嵌入向量探索**: 提供 UMAP/t-SNE 可视化, 可发现"输入分布异常"(比如有用户开始用新语种)
3. **评估管线**: 内置 RAG 评估(检索准确率、回答忠实度), 幻觉检测
4. **数据集对比**: 同一组测试题在不同模型版本的表现对比
5. **离线 + 在线评估**: 既可以跑批量评估, 也可以实时监控生产流量

## 与我们项目的关系
**关卡 6(黑匣子审计)**: Phoenix 与 Langfuse 是"二选一或并行使用"的关系。Phoenix 的 OTel 原生支持是大优势 —— 如果我们决定走"OTel GenAI 标准"路线, Phoenix 接入零成本。建议:
- 如果团队侧重"运营 / 产品迭代": 选 Langfuse
- 如果团队侧重"模型评估 / 数据分析": 选 Phoenix
- 政企项目通常需要严肃的评估报告, Phoenix 可能更合适
也可以两者并行: Phoenix 做评估和分析, Langfuse 做生产监控。

## 学习建议
1. 上手: `pip install arize-phoenix && phoenix.launch_app()` 即可
2. 看官方教程的 "LLM Traces" 和 "Evaluation Datasets" 章节
3. 与 OpenInference (Arize 推动的 OTel 扩展) 配合使用
