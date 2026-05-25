# OpenTelemetry GenAI 语义规范

## 基本信息
- **类型**: 业界规范(CNCF 项目)
- **官方链接**: https://opentelemetry.io/docs/specs/semconv/gen-ai/
- **GitHub**: https://github.com/open-telemetry/semantic-conventions/tree/main/docs/gen-ai
- **许可证**: Apache 2.0

## 这是什么
OpenTelemetry (简称 OTel) 是 CNCF 旗下的"可观测性事实标准", 几乎所有云原生系统都用它来记录 metrics, logs, traces。它做的事:统一定义"一个日志/指标应该叫什么名字、字段有哪些"。

GenAI 语义规范是 OTel 针对"生成式 AI 应用"的专门扩展, 它定义了一组标准字段名, 让所有 LLM 应用产出的日志能被同一套工具(Grafana, Jaeger, Datadog 等)统一可视化和告警。这相当于给 LLM 行业制定了一个"日志普通话"——之前每个团队/产品自己造词(有的叫 `model_name`, 有的叫 `model_id`, 有的叫 `llm_model`), 互相对不上; 现在大家都叫 `gen_ai.request.model`, 工具就能跨产品工作。

规范目前仍在 stable + experimental 状态, 大头已稳定, 部分高级字段(如多模态)仍在演化。

## 关键能力
1. **统一字段命名**: 7 个核心字段成为业界默认:
   - `gen_ai.request.model`: 请求的模型名(如 "gpt-4o", "claude-3.5-sonnet")
   - `gen_ai.usage.input_tokens` / `gen_ai.usage.output_tokens`: token 计数
   - `gen_ai.response.finish_reasons`: 结束原因(stop / length / content_filter / tool_calls)
   - `gen_ai.system_instructions`: 系统提示词内容
   - `gen_ai.input.messages` / `gen_ai.output.messages`: 完整对话历史
   - `gen_ai.tool.name`: 工具调用名
2. **trace 语义**: 定义"LLM 一次调用"应当是一个 span, 工具调用是子 span
3. **多供应商一致性**: 覆盖 OpenAI, Anthropic, Bedrock, Vertex, Cohere 等主流供应商
4. **与现有可观测性工具直接对接**: Grafana / Loki / Tempo / Datadog 都已原生支持
5. **可扩展**: 厂商可以加自有字段, 但必须用 `gen_ai.` 前缀

## 与我们项目的关系
**关卡 6(黑匣子审计) + 运营回路**: 这是黑匣子日志格式的"标准答案"。我们应当采用 OTel GenAI 语义作为日志骨架, 在 7 个核心字段之上增加政企扩展字段(参见 README.md "审计日志 7 字段扩展"建议)。好处:
1. 日志可被 Grafana 等现成工具直接消费, 不用自造轮子
2. 监管/审计方拿到日志后可用通用工具分析, 不绑定我们的私有格式
3. 跨供应商: 我们项目可能同时调用 OpenAI 和国产模型, OTel 字段统一后无缝切换

## 学习建议
1. 通读规范 https://opentelemetry.io/docs/specs/semconv/gen-ai/ (1 小时即可)
2. 看 OpenLLMetry / OpenLIT 这两个开源 SDK 的实现
3. 把关卡 6 现有字段映射到 OTel 标准, 找出缺漏 + 政企扩展点
