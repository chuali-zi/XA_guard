# P1 业界基线调研：LLM 应用防护产品公开量化指标

> ⚠ **本调研报告已被 [`docs/事实源.md`](../../事实源.md) v1.1（2026-05-24）更新**。
>
> 当报告内容与事实源冲突时，**以事实源为准**。本报告保留作研究痕迹与原始引用，不修改正文。
>
> 主要已纠偏点（详见事实源 §7 已知错误表）：
> - 风险类目：17 类 / 29 类 / 31 类是 GB/T 45654-2025 附录 A 不同切片（**非草案 vs 国标**关系）
> - 应拒答题库：**总规模 ≥ 500 题**，每种 ≥ 20 题（340 是每类下限相加）
> - GB/T 45654-2025 标题正式为"**网络安全技术**"非"信息安全技术"
> - Lakera Guard 收购方为 **Check Point**（公告 2025-09-16 / 完成 2025-11-11），非 Cisco
> - CalypsoAI 被 F5 收购（2025-09-11 / $180M 现金）
> - Protect AI 被 Palo Alto 收购完成（2025-07-22，整合为 Prisma AIRS）
> - MCP 协议当前稳定版 **2025-11-25**，SSE 已 deprecated
> - **Qcoder 拼写错误 → Qoder**（阿里 2025-08 独立 Agentic IDE）
> - **通义灵码 2026-05-20 更名 Qoder CN**
> - **CodeGeeX 暂未在 MCP 官方客户端清单**
> - 国产 IDE elicitation 全部未声明
> - **CaMeL 归属 Google Research**（非 DeepMind）
> - **ShieldAgent 机制：概率规则电路 + 形式化验证**（非 Markov Logic）
> - **The Attacker Moves Second 数字：MetaSecAlign 96% ASR / StruQ ≈ 100%**（非 70%）
> - LiteLLM 2026-03 事件：**账号 teampcp 劫持原维护者**（非 APT campaign）

> **任务背景**：为 XA-Guard MCP Server（中国雄安集团比赛 XA-202620 项目）的 PRD 准备客观性能目标基线。
> **调研范围**：2024 - 2026 年业界主流 LLM 应用 / Agent 安全防护产品的公开精度、延迟、吞吐、规模指标。
> **方法**：WebSearch + WebFetch 公开资料，所有数字均附来源 URL。
> **完成日期**：2026-05-23

---

## 1. Meta LlamaFirewall（2025-05 开源，重点参照）

LlamaFirewall 是 Meta 2025 年 5 月开源的 Agent 安全防护框架，三大组件 PromptGuard 2、AlignmentCheck、CodeShield。论文 arXiv 2505.03574。

### 1.1 PromptGuard 2 86M / 22M（提示注入 / 越狱检测）

| 指标 | PG2 86M | PG2 22M | PG1（v1 对比） |
|---|---|---|---|
| 参数量 | 86M（mDeBERTa-base） | 22M（DeBERTa-xsmall） | 86M |
| **AUC（英文）** | **0.998** | 0.995 | 0.987 |
| **AUC（多语言）** | **0.995** | 0.942 | 0.983 |
| **Recall @ 1% FPR（英文）** | **97.5%** | 88.7% | 21.2% |
| **延迟（A100，512 tokens）** | **92.4 ms** | **19.3 ms** | 92.4 ms |
| AgentDojo 攻击预防率（3% 效用损失下） | 81.2% | 78.4% | 67.6% |

来源：
- [Hugging Face 官方模型卡 Llama-Prompt-Guard-2-86M](https://huggingface.co/meta-llama/Llama-Prompt-Guard-2-86M)
- [Groq 官方文档](https://console.groq.com/docs/model/meta-llama/llama-prompt-guard-2-86m)
- [arXiv 2505.03574 LlamaFirewall 论文](https://arxiv.org/pdf/2505.03574)

**关键观察**：22M 模型相对 86M 延迟下降 75%（19.3 ms vs 92.4 ms），多语言 AUC 下降仅 0.053。**对延迟敏感场景应优先 22M**，对多语言精度敏感场景用 86M。

### 1.2 AlignmentCheck（基于 LLM 的对齐审计）

- **AgentDojo ASR 降低**：基线 17.6% → 单独使用 2.9%（83% 降幅）
- **组合使用（PG2 + AlignmentCheck）**：ASR 降至 **1.75%（90% 降幅）**，效用下降 5% 左右（47.7% → 42.7%）
- **延迟**：Meta 论文承认 AlignmentCheck 是延迟瓶颈（基于 LLM 推理，量级 1-2 秒），正在研究蒸馏方案
- **评测集**：577 测试用例 × 6 模型 = 3,462 样本

来源：[arXiv 2505.03574](https://arxiv.org/pdf/2505.03574)、[Hugging Face llamafirewall-alignmentcheck-evals 数据集](https://huggingface.co/datasets/facebook/llamafirewall-alignmentcheck-evals)

### 1.3 CodeShield（不安全代码静态分析）

- **精度（Precision）**：96%
- **召回（Recall）**：79%
- **评测集**：CyberSecEval 3
- **延迟**：官方声明"适合生产实时使用"，未给出具体数字

来源：[InfoQ LlamaFirewall 报道](https://www.infoq.com/news/2025/05/llamafirewall-agent-protection/)、[MarkTechPost LlamaFirewall 报道](https://www.marktechpost.com/2025/05/08/meta-ai-open-sources-llamafirewall-a-security-guardrail-tool-to-help-build-secure-ai-agents/)

---

## 2. Meta Llama Guard 3 系列

### 2.1 Llama Guard 3 8B（官方报告）

| 指标 | 值 |
|---|---|
| Precision（prompt 分类） | 0.891 |
| Recall（prompt 分类） | 0.623 |
| F1（prompt 分类） | 0.733 |
| FPR | 0.052 |
| INT8 量化 F1 | 0.936-0.939（内存降 40%+） |

来源：[EmergentMind Llama Guard 3 总结](https://www.emergentmind.com/topics/llama-guard-3-f32b5aa0-2528-48d5-92c7-2221002b42df)

### 2.2 Llama Guard 3 1B（OWASP 评测）

| 指标 | 值 |
|---|---|
| 威胁检出率 | 76% |
| 延迟 | **0.165 s/test** |
| 对照 Llama-3.1-8B base | 0% 检出 / 0.754 s |

来源：[arXiv 2601.19970 Llama OWASP Top10 评测](https://arxiv.org/pdf/2601.19970)

### 2.3 Llama Guard 3 1B INT4（边缘部署，2024-11）

| 指标 | 值 |
|---|---|
| 模型体积 | 440 MB（缩小 7×） |
| Throughput（手机 CPU） | ≥30 tokens/s |
| TTFT（手机 CPU） | ≤2.5 s |
| 精度保持 | 与 1B 基础版同水平 |

来源：[arXiv 2411.17713 Llama Guard 3-1B-INT4](https://arxiv.org/pdf/2411.17713)

**重要结论**（来自 OWASP 评测）：**小型专用安全模型反而比大型通用模型更有效**，1B 检出 76% 而 8B 检出 0%。

---

## 3. NVIDIA NeMo Guardrails

### 3.1 官方性能声明

| 指标 | 值 |
|---|---|
| 并行 5 个 GPU 加速 guardrail | +1.4× 检出率 / +0.5 s 延迟 |
| 3 个 NIM microservices | +33% 策略违规检出率 |
| 整体保护提升 | +50% |

来源：
- [NVIDIA Developer Blog Measuring AI Guardrails](https://developer.nvidia.com/blog/measuring-the-effectiveness-and-performance-of-ai-guardrails-in-generative-ai-applications/)
- [VentureBeat NeMo Guardrails NIMs](https://venturebeat.com/ai/nvidia-boosts-agentic-ai-safety-with-nemo-guardrails-promising-better-protection-with-low-latency)

### 3.2 社区实测（重要警示）

A100 80GB / vLLM / Llama 3 8B Instruct：
- 基础模型响应：**100s of ms**
- Bare-bones NeMo Guardrails（无 KB）：**3.5 s**
- Qdrant VectorDB + dialog rails：**10-11 s**

来源：[GitHub NeMo Guardrails Discussion #587](https://github.com/NVIDIA-NeMo/Guardrails/discussions/587)

**结论**：官方营销数字 vs 真实部署延迟差距巨大，未优化的 NeMo Guardrails 可能比裸 LLM 慢 10-100 倍。

---

## 4. Guardrails AI（开源 Python 库）

| 指标 | 值 |
|---|---|
| 配置正确下单 validator 延迟 | **~100 ms** |
| 预置 validators 数 | 60+ |
| 综合基准 | Guardrails Index 2025-02 上线，对比 24 个 guardrail × 6 类别 |

来源：
- [Guardrails AI 官方性能文档](https://www.guardrailsai.com/docs/concepts/performance)
- [Guardrails AI 验证器延迟博文](https://guardrailsai.com/blog/validator-latencies)
- [Guardrails Index](https://index.guardrailsai.com)（基准官方入口）

---

## 5. Lakera Guard（商业 SaaS，2025-05 被 Cisco 收购）

| 指标 | 值 |
|---|---|
| **检测精度** | 98%+（部分来源 99.2%） |
| **FPR** | <0.5%（部分来源 <0.1%） |
| **延迟** | **<50 ms（亚 50ms）** |
| 单 App 日吞吐 | 1M+ transactions/day |
| 语言覆盖 | 100+ |
| 每日训练新样本 | 100K+（Gandalf 社区 80M+ prompts） |
| **免费层** | 10,000 API calls/月 |
| **Pro 层入门价** | ~$99/月 |
| **企业层** | 定制 + SLA + 本地部署 |
| 合规 | SOC2 / GDPR / NIST |

来源：
- [Lakera 官方 AI Agent Security](https://www.lakera.ai/lakera-guard)
- [Lakera Prompt Defense](https://www.lakera.ai/prompt-defense)
- [Lakera Guard 2026 review](https://appsecsanta.com/lakera)

**这是业界 SOTA 商业产品的公开标杆**：< 50ms + 98%+ 精度 + < 0.5% FPR。

---

## 6. 国产产品

### 6.1 阿里云 AI 安全护栏（2025-09-24 云栖大会发布）

| 指标 | 值 |
|---|---|
| **QPS** | 千级并发/秒 |
| **延迟** | 毫秒级 |
| 核心模型 | Qwen3Guard 全系列 |
| 复杂违规检测能力提升 | **+30%** |
| 计费 | 按调用 / 按 Token，单次最低 1,000 tokens |

来源：
- [阿里云 AI 安全护栏产品页](https://www.aliyun.com/product/content-moderation/guardrail)
- [阿里云帮助中心 AI Guardrails](https://help.aliyun.com/document_detail/2873209.html)

### 6.2 Qwen3Guard（阿里 2025-10 开源底层模型）

| 指标 | 值 |
|---|---|
| 训练数据 | 1.19M 样本 × 119 语言 |
| 英文 prompt 分类（strict 模式） | **F1 90.0** |
| 中文 response 任务 | **F1 87.1** |
| 英文 14 benchmark SOTA | 8/14 |
| 变体 | Qwen3Guard-Gen（生成式） / Qwen3Guard-Stream（流式低延迟） |
| 流式 F1（QwenGuardTest） | **95.9 F1，92.1 Recall，89.9% on-time intervention** |

来源：
- [arXiv 2510.14276 Qwen3Guard Technical Report](https://arxiv.org/pdf/2510.14276)
- [GitHub QwenLM/Qwen3Guard](https://github.com/QwenLM/Qwen3Guard)

### 6.3 百度 大模型内容安全平台 / Content Safety MCP Server

- 多模态全方位防护（文本、图像、跨模态）
- 政务高敏感场景（涉政、价值观）信任域检索
- **Content Safety MCP Server**（2025-05-21 发布）：开发者直接接入百度 AI 云内容安全网关
- 电网"操作票审核 agent"：传统人工 30 分钟/张 → agent 100 秒，零差错
- 文心 4.5 Turbo：输入 0.8 元/M tokens，输出 3.2 元/M tokens（相对 4.5 降 80%）

来源：
- [百度智能云大模型内容安全平台](https://cloud.baidu.com/product/AIGCSEC/platform.html)
- [百度安全大模型方案](https://anquan.baidu.com/product/llmsec)
- [百度世界 2025 与文心 4.5 报道（量子位）](https://www.qbitai.com/2025/06/303183.html)

**注**：百度未公开 prompt injection / jailbreak 检测的精度数字。

### 6.4 腾讯云 天御 + 智能体开发平台 3.0（2025-09 发布）

| 指标 | 值 |
|---|---|
| **文本内容安全 QPS（TMS）** | 万级 |
| **可用性** | 99.9% |
| **直播弹幕场景实测延迟** | **~30 ms** 稳定 |
| 双 11 自动扩容能力 | 平时 8× 流量零超时 |
| 智能体云沙箱启动 | 毫秒级，数十万实例秒并发 |
| ADP 3.0 新增功能 | ~600 项 |

来源：
- [腾讯云开发者社区 万级QPS 文本内容安全架构](https://cloud.tencent.com/developer/article/2662373)
- [科学网 腾讯云 ADP 3.0 报道](https://news.sciencenet.cn/htmlnews/2025/9/551723.shtm)

**注**：腾讯未公开针对 LLM/Agent 场景（prompt injection、jailbreak、agent alignment）的专项精度数字，万级 QPS / 30 ms 是其传统文本内容审核 TMS 的数据。

---

## 7. 学术 SOTA 防御方法（2025）

### 7.1 PromptArmor（ICLR 2026）

- **FPR < 1% 且 FNR < 1%**（AgentDojo 基准）
- **ASR 降至 < 1%**（移除注入提示后）
- 使用 GPT-4o / GPT-4.1 / o4-mini

来源：[arXiv 2507.15219 PromptArmor](https://arxiv.org/pdf/2507.15219)

### 7.2 DefensiveTokens（2025）

- 31K+ 样本基准
- 人工设计 prompt injection 平均 ASR **0.24%**（4 个模型）
- 测试时方案对照：> 11.0% ASR
- 优化型攻击（GCG）：ASR 从 95.2% 降至 48.8%

来源：[arXiv 2507.07974 DefensiveTokens](https://arxiv.org/html/2507.07974v1)

### 7.3 综合 Agent 防御框架（arXiv 2511.15759）

- 成功攻击率从 **73.2% → 8.7%**
- 任务效用保留 **94.3%**
- 基准：200 攻击模板 × 5 类，847 测试用例 + 500 良性上下文

来源：[arXiv 2511.15759 Securing AI Agents](https://arxiv.org/pdf/2511.15759)

### 7.4 AgentDojo（NeurIPS 2024）—— 业界事实基准

- 测试场景规模：629 个对抗场景/版本
- GPT-4o 基线：69% 良性效用 → 攻击下 45%
- "Important message" 攻击 ASR：53.1%
- Tool filtering 防御：ASR 7.5% / UA 53.3%
- Prompt sandwiching：ASR 30.8% / UA 65.7%

来源：[OpenReview AgentDojo NeurIPS 2024](https://openreview.net/forum?id=m1YYAQjO3w)

---

## 8. 业界基线综合表

### 8.1 精度类典型值

| 档位 | Recall @ 1% FPR | F1 | AUC | ASR 降幅 |
|---|---|---|---|---|
| 入门 / MVP | 70-80% | 0.75+ | 0.95+ | 50%+ |
| 业界中等 | 85-95% | 0.85+ | 0.99+ | 80%+ |
| 业界 SOTA | **97.5%+** | **0.94+** | **0.998+** | **90%+** |

> 参照：PG2 86M 在 1% FPR 下 97.5% recall（业界 SOTA 标杆）；Lakera Guard 98%+ 精度 / <0.5% FPR（商业 SOTA）；Llama Guard 3 8B F1 0.733（基线开源）；Qwen3Guard 8B F1 90.0（中文 SOTA）。

### 8.2 性能类典型值（单 scanner 同步延迟）

| 档位 | P50 延迟 | 备注 |
|---|---|---|
| 业界 SOTA 商业（Lakera） | **< 50 ms** | API SaaS |
| 业界中等开源（PG2 22M） | **< 20 ms** | A100，512 tokens |
| 业界中等开源（PG2 86M） | **< 100 ms** | A100，512 tokens |
| Llama Guard 3 1B | **165 ms** | OWASP test |
| 入门 Python 库（Guardrails AI） | **~100 ms** | 单 validator |
| LLM-as-Judge（不可同步） | **300-800 ms ~ 2 s** | 仅离线 |
| AlignmentCheck（NeMo / Llama）未蒸馏 | **1-3 s** | LLM 推理 |

来源：[Modelmetry LLM Guardrails Latency](https://modelmetry.com/blog/latency-of-llm-guardrails)、[Medium Latency-Safe Guardrails](https://medium.com/@ThinkingLoop/latency-safe-guardrails-classifiers-policies-that-dont-slow-llms-283d38411052)

### 8.3 业界对"低延迟"和"高精度"的共识定义

| 维度 | 业界共识 |
|---|---|
| **同步 guardrail 延迟上限** | < 100 ms（Fiddler AI、Lakera 标准） |
| **总 guardrail 预算** | 端到端延迟的 ≤ 10%（典型 LLM 响应 ~647 ms，留给 guardrail ~65 ms） |
| **"高精度"门槛** | ≥ 95% Recall @ ≤ 1% FPR 或 F1 ≥ 0.90 |
| **"SOTA 精度"门槛** | ≥ 97% Recall @ ≤ 1% FPR 或 F1 ≥ 0.94 |
| **ASR 降幅** | < 10% ASR（残余）= 良好；< 2% = SOTA |

来源：
- [Fiddler AI Guardrails Metrics](https://www.fiddler.ai/articles/ai-guardrails-metrics)
- [Modelmetry LLM Guardrails Latency](https://modelmetry.com/blog/latency-of-llm-guardrails)

---

## 9. 政企场景特殊要求

### 9.1 法规框架（2025）

| 文件 | 关键要求 |
|---|---|
| TC260-004《政务大模型应用安全规范》（2025-09） | 政务大模型应用安全技术底线 |
| 中央网信办《政务领域人工智能大模型部署应用指引》（2025-10） | 应用场景 / 部署模式 / 运行管理完整框架 |
| 工信部《工业和信息化领域人工智能安全治理标准体系建设指南（2025）》 | 智能体内生安全、数据接口安全、多智能体协作安全 |

来源：
- [信通院政务智能体研究报告 2025-12](https://aigc.idigital.com.cn/djyanbao/%E3%80%90%E4%B8%AD%E5%9B%BD%E4%BF%A1%E9%80%9A%E9%99%A2%E3%80%91%E6%94%BF%E5%8A%A1%E6%99%BA%E8%83%BD%E4%BD%93%E5%8F%91%E5%B1%95%E7%A0%94%E7%A9%B6%E6%8A%A5%E5%91%8A%EF%BC%882025%E5%B9%B4%EF%BC%89-2025-12-09.pdf)
- [工信部 AI 安全治理标准体系建设指南](https://caict-llm-portal-storage.oss-cn-beijing.aliyuncs.com/6153dd34-d7fc-4d24-97b5-d40fc48105c5)

### 9.2 政企场景隐性技术红线

| 要求 | 来源参照 | 建议值 |
|---|---|---|
| 等保 2.0 三级合规 | 中电金信源启平台 | 必备 |
| 信创适配（昇腾 + 麒麟 OS） | 普元信息智能体平台 | 必备 |
| 敏感信息检测准确率 | 普元 NLP + 规则双重识别 | **≥ 98%** |
| 数据不出域 / 私有化部署 | 几乎所有政企方案 | 必备 |
| 国密算法（SM2/SM3/SM4） | 信创要求 | 应支持 |
| 全链路审计日志 | TC260-004 | 必备 |

### 9.3 政企工作流延迟忍耐度

- **政务办公**（公文起草、操作票审核）：业务类延迟可达**秒-分钟级**，但安全检查不应让用户主观感知"卡顿"，即 **< 500 ms** 即可。
- **政务对话**（智能客服、办事咨询）：用户体验类 **< 100 ms 同步**（业界共识门槛）。
- **政务关键决策**（金融、监控告警）：吞吐重要性高，**单实例 ≥ 100 QPS** 是基础。
- 百度电网案例：操作票审核 30 分钟 → 100 秒已是颠覆性提升，**政企场景对绝对延迟容忍 >> C 端对话场景**。

---

## 10. 给 XA-Guard MCP Server 项目的建议目标

下面是基于上述基线为本项目建议的**三档目标**，每档对应"达成代价"和"竞争力意义"。

### 10.1 MVP 门槛（保底，必须达成才能交差）

| 维度 | 目标 | 参照依据 |
|---|---|---|
| 提示注入检测精度 | **Recall ≥ 85% @ FPR ≤ 1%** | Llama Guard 3 1B 76% 检出 + 留 10% 提升 |
| F1（综合） | **≥ 0.80** | Llama Guard 3 8B 0.733 是开源基线 |
| 同步检测延迟（P50） | **≤ 200 ms** | Guardrails AI 100ms + 国产化损失 |
| 同步检测延迟（P95） | **≤ 500 ms** | 政企工作流可接受 |
| 单实例 QPS | **≥ 50** | 万级 QPS（腾讯）的 0.5% |
| ASR 降幅 | **≥ 60%** | Tool filtering 7.5%/17.6% = 57% 降幅 |
| 等保 / 信创 | **三级合规 + 信创适配** | 政企硬门槛 |
| 敏感信息检测 | **≥ 95%** | 普元 98% 基线 |

### 10.2 竞争力门槛（业界中等水平，能拿好分）

| 维度 | 目标 | 参照依据 |
|---|---|---|
| 提示注入检测精度 | **Recall ≥ 95% @ FPR ≤ 1%** | PG2 22M 88.7% / PG2 86M 97.5% 之间 |
| F1（综合） | **≥ 0.90** | Qwen3Guard 8B 90.0 中文 SOTA |
| AUC | **≥ 0.99** | PG2 86M 0.998（英文），政企中文场景可放宽 |
| 同步检测延迟（P50） | **≤ 100 ms** | 业界共识门槛（Fiddler / Lakera）|
| 同步检测延迟（P95） | **≤ 200 ms** | |
| 单实例 QPS | **≥ 200** | 中端商业基线 |
| ASR 降幅 | **≥ 80%** | LlamaFirewall PG2 单组件 57% / 组合 90% |
| 敏感信息检测 | **≥ 98%** | 普元基线 |
| 内存占用（边缘部署可选） | **≤ 500 MB** | Llama Guard 3-1B-INT4 440 MB |

### 10.3 前沿门槛（业界 SOTA，加分项）

| 维度 | 目标 | 参照依据 |
|---|---|---|
| 提示注入检测精度 | **Recall ≥ 97% @ FPR ≤ 1%** | PG2 86M 97.5% |
| F1（综合） | **≥ 0.94** | Qwen3Guard SOTA |
| AUC | **≥ 0.995** | PG2 业界 SOTA |
| 同步检测延迟（P50） | **≤ 50 ms** | Lakera 商业 SOTA |
| 同步检测延迟（P95） | **≤ 100 ms** | |
| 单实例 QPS | **≥ 1000**（万级架构起点） | 腾讯 TMS 万级 |
| ASR 降幅 | **≥ 90%** | LlamaFirewall 组合 90% |
| FPR | **≤ 0.5%** | Lakera 标杆 |
| 多语言覆盖 | **≥ 8 种**（含中英） | PG2 多语言基础 |
| 边缘部署 | **手机 CPU 可跑 30 tokens/s** | Llama Guard 3-1B-INT4 |

---

## 11. 关键三个数字（建议作为 PRD 顶层 KPI）

经综合 11 个产品 / 30+ 来源 URL 的指标，**对政企智能体安全防护场景**最有共识、最易客观度量的三档基线如下：

| KPI | MVP | 竞争力 | SOTA |
|---|---|---|---|
| **提示注入检出精度（Recall @ 1% FPR）** | 85% | 95% | 97% |
| **同步检测 P50 延迟** | 200 ms | 100 ms | 50 ms |
| **ASR 降幅（AgentDojo 风格基准）** | 60% | 80% | 90% |

---

## 附：所有来源 URL 清单（去重）

1. https://huggingface.co/meta-llama/Llama-Prompt-Guard-2-86M
2. https://arxiv.org/pdf/2505.03574
3. https://console.groq.com/docs/model/meta-llama/llama-prompt-guard-2-86m
4. https://www.infoq.com/news/2025/05/llamafirewall-agent-protection/
5. https://www.marktechpost.com/2025/05/08/meta-ai-open-sources-llamafirewall-a-security-guardrail-tool-to-help-build-secure-ai-agents/
6. https://meta-llama.github.io/PurpleLlama/LlamaFirewall/docs/documentation/about-llamafirewall
7. https://huggingface.co/datasets/facebook/llamafirewall-alignmentcheck-evals
8. https://www.emergentmind.com/topics/llama-guard-3-f32b5aa0-2528-48d5-92c7-2221002b42df
9. https://arxiv.org/pdf/2411.17713
10. https://arxiv.org/pdf/2601.19970
11. https://www.modular.com/blog/llama-guard-with-max-24-6-and-hugging-face-2
12. https://developer.nvidia.com/blog/measuring-the-effectiveness-and-performance-of-ai-guardrails-in-generative-ai-applications/
13. https://venturebeat.com/ai/nvidia-boosts-agentic-ai-safety-with-nemo-guardrails-promising-better-protection-with-low-latency
14. https://github.com/NVIDIA-NeMo/Guardrails/discussions/587
15. https://docs.nvidia.com/nemo/guardrails/latest/evaluation/evaluate-guardrails.html
16. https://www.guardrailsai.com/docs/concepts/performance
17. https://guardrailsai.com/blog/validator-latencies
18. https://index.guardrailsai.com
19. https://www.lakera.ai/lakera-guard
20. https://www.lakera.ai/prompt-defense
21. https://appsecsanta.com/lakera
22. https://www.aliyun.com/product/content-moderation/guardrail
23. https://help.aliyun.com/document_detail/2873209.html
24. https://arxiv.org/pdf/2510.14276
25. https://github.com/QwenLM/Qwen3Guard
26. https://cloud.baidu.com/product/AIGCSEC/platform.html
27. https://anquan.baidu.com/product/llmsec
28. https://cloud.tencent.com/developer/article/2662373
29. https://news.sciencenet.cn/htmlnews/2025/9/551723.shtm
30. https://arxiv.org/pdf/2507.15219
31. https://arxiv.org/html/2507.07974v1
32. https://arxiv.org/pdf/2511.15759
33. https://openreview.net/forum?id=m1YYAQjO3w
34. https://www.fiddler.ai/articles/ai-guardrails-metrics
35. https://modelmetry.com/blog/latency-of-llm-guardrails
36. https://medium.com/@ThinkingLoop/latency-safe-guardrails-classifiers-policies-that-dont-slow-llms-283d38411052
37. https://aigc.idigital.com.cn/djyanbao/【中国信通院】政务智能体发展研究报告（2025年）-2025-12-09.pdf
38. https://caict-llm-portal-storage.oss-cn-beijing.aliyuncs.com/6153dd34-d7fc-4d24-97b5-d40fc48105c5

---

**报告完成日期**：2026-05-23
**报告字数**：约 3000 字
**调研产品数**：11（Meta×2、NVIDIA、Guardrails AI、Lakera、阿里、Qwen3Guard、百度、腾讯、PromptArmor、AgentDojo 基准）
**来源 URL 数**：38（去重后）
