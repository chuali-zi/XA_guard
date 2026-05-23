# OWASP Top 10 for Large Language Model Applications 2025

## 基本信息
- **发布机构**: OWASP GenAI Security Project
- **发布时间**: 2024 年 11 月（v2025 正式版）
- **官方链接**: https://genai.owasp.org/llm-top-10/
- **PDF 直链**: https://owasp.org/www-project-top-10-for-large-language-model-applications/assets/PDF/OWASP-Top-10-for-LLMs-v2025.pdf
- **是否强制（政企场景）**: 推荐（业界事实标准）

## 一句话总结
大模型应用的"十大安全风险"清单，对标 OWASP Web Top 10，业界事实标准。

## 这是什么

OWASP 是 Web 安全领域的最权威非营利机构。他们的 **OWASP Top 10**（Web 应用十大风险）是 20+ 年的业界标准。

2023 年随着大模型应用爆发，OWASP 启动了 **GenAI Security Project**，推出 **OWASP Top 10 for LLM Applications**——大模型应用版的 Top 10。每年更新。

## 2025 版十大风险

| 排序 | 风险 ID | 名称 | 与我们项目对应 |
|---|---|---|---|
| 1 | LLM01 | Prompt Injection（提示注入） | **关卡 1 门口安检** |
| 2 | LLM02 | Sensitive Information Disclosure（敏感信息泄漏） | **关卡 4 三色信息流污点** |
| 3 | LLM03 | Supply Chain Vulnerabilities（供应链漏洞） | **AIBOM 准入网关** |
| 4 | LLM04 | Data and Model Poisoning（数据与模型投毒） | **关卡 1 RAG 防御 + AIBOM** |
| 5 | LLM05 | Improper Output Handling（输出处理不当） | **关卡 5 沙箱 + CodeShield** |
| 6 | LLM06 | Excessive Agency（过度自主） | **关卡 2 HITL + 关卡 3 Policy DSL** |
| 7 | LLM07 | System Prompt Leakage（系统提示泄漏）★ 新 | **关卡 4** |
| 8 | LLM08 | Vector and Embedding Weaknesses（向量和嵌入弱点）★ 新 | **关卡 4** |
| 9 | LLM09 | Misinformation（错误信息） | **关卡 6 审计 + LLM 水印** |
| 10 | LLM10 | Unbounded Consumption（无限消耗，DoS/资源耗尽） | （边缘，未直接覆盖） |

## 关键新增（2025 vs 2024）

- **LLM07 System Prompt Leakage**：新增项，强调系统提示词泄漏的危害
- **LLM08 Vector and Embedding Weaknesses**：新增项，关注 RAG 向量数据库的弱点
- **LLM03 Supply Chain**：从 2024 版的较后位置**提到第 3 位**——这是 LiteLLM 2026-03 事件后业界共识升级

## 我们项目里的用法

**这是我们 30 页方案"问题陈述"章节的最佳引子**：

「OWASP Top 10 for LLM Apps 2025 列出了大模型应用的十大风险，本方案的 6 关卡架构覆盖其中 9 项（LLM01-LLM09）」

然后画一张映射表（如上）作为正文。这一张表能让评委 30 秒内理解我们方案的**完整性**和**对标行业最佳实践**。

## 学习建议

- **必读**：每个风险类的 Description + Common Examples + Prevention（2 小时可看完）
- **可跳过**：完整 References（数百条）
- **关键**：每个风险至少要能在演示视频里举出 1 个对应场景

## 与本目录其他资源的关系

- **NIST-AI-600-1**：另一个"风险类目"清单，更学术，OWASP 更工业
- **TC260-003 / GBT-45654**：中国版的对应清单
- **../03_supply_chain/LiteLLM-Incident-2026.md**：LLM03 的关键事件案例
