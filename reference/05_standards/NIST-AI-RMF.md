# NIST AI Risk Management Framework 1.0（美国国家标准与技术研究院 AI 风险管理框架）

## 基本信息
- **发布机构**: NIST（美国国家标准与技术研究院）
- **发布时间**: 2023 年 1 月
- **当前版本**: 1.0（2023-01）
- **法律层级**: 自愿性指南（不是强制法律，但事实标准）
- **官方链接**: https://www.nist.gov/itl/ai-risk-management-framework
- **PDF 直链**: https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf

## 一句话总结
美国版"AI 风险管理操作手册"，提出 GOVERN/MAP/MEASURE/MANAGE 四功能循环。

## 这是什么

NIST 是美国最权威的标准制定机构之一（互联网、加密、网络安全很多标准都是他们出的）。

NIST AI RMF 1.0 是他们针对 AI 系统给出的**风险管理框架**——告诉企业、政府、研究机构怎么系统化地管理 AI 风险。

核心是**四个功能（Function）的循环**：

1. **GOVERN（治理）**：组织层面建立 AI 风险管理的政策、流程、责任分工
2. **MAP（映射）**：识别具体 AI 系统的风险来源、风险事件、影响人群
3. **MEASURE（度量）**：用具体指标度量风险水平
4. **MANAGE（管理）**：实施缓解、监控、回应

每个功能下面又分若干 **Category** 和 **Subcategory**，构成一个完整的实施清单（清单约 70 项）。

## 关键概念

- **可信 AI 七要素**：有效可靠 / 安全 / 韧性 / 可问责透明 / 可解释可解读 / 增强隐私 / 公平减偏
- **风险管理生命周期**：与"AI Lifecycle"（数据、模型、部署、监控）对齐

## 与我们项目的关系

NIST AI RMF 是**国际通用的对标框架**——我们 30 页方案的"国际对标"章节可以画一张图：

```
我们的 6 关卡 → 对应 NIST AI RMF 的哪些 Subcategory
```

具体对应：
- 入口防御 / 内容审查 → MEASURE 2.7（Safety）
- 工具调用约束 / HITL → MANAGE 4.2（Tradeoff）
- 审计 / 溯源 → GOVERN 4.3（Records）+ MAP 5.2（Documentation）
- 评测基准 → MEASURE 2.x 全系列

## 学习建议

- **必看**：Executive Summary + Section 3（Four Functions）
- **跳过**：完整清单 70 项的细节
- **配套**：NIST AI 600-1（生成式 AI 专门 Profile）

## 与本目录其他资源的关系

- **NIST-AI-600-1**：本框架的生成式 AI 子项
- **ISO-42001-2023**：国际通用的 AI 管理体系标准（与 NIST AI RMF 互补，前者是认证标准，后者是指南）
