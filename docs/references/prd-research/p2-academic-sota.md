# P2 学术 SOTA 基准量化数据调研

> ⚠ **本调研报告已被 [`docs/source-of-truth/事实源.md`](../../source-of-truth/事实源.md) v1.1（2026-05-24）更新**。
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

> **任务**：为雄安比赛 XA-202620 的 PRD 设定合理的评测目标基线，避免过度承诺也避免过于保守。
> **时间**：2026-05-23
> **范围**：2024-2026 年 LLM 智能体安全主流基准的 SOTA 数字，以及业界防御方案在加固后的 ASR 改善幅度。
> **方法**：WebSearch / WebFetch 对原论文与官方资源做交叉核对。所有数字附来源 URL。

---

## 0. 速览：3 个最关键基线（写到 PRD 必引）

| 数字 | 含义 | 来源 |
|---|---|---|
| **84.30% Mixed-Attack ASR** | LLM 智能体在 ASB（ICLR 2025）9 万次实测下的平均最高 ASR；GPT-4o / Qwen2-72B 接近 100% | [arXiv 2410.02644](https://arxiv.org/abs/2410.02644) |
| **没有任何模型 > 60 分** | 清华 Agent-SafetyBench 评测 16 个主流 LLM agent，全部不及格 | [arXiv 2412.14470](https://arxiv.org/abs/2412.14470) |
| **AgentDojo 目标 ASR：GPT-4o 47.7% / Claude 3 Opus 11.3%** | 同基准最佳商业模型仍有 11% 被注入，开源模型显著更差 | [arXiv 2406.13352](https://arxiv.org/abs/2406.13352) |

PRD 引用范式建议：

> 即便是当前最强的商业模型，在 AgentDojo 上目标攻击成功率仍达 11%-48%（[Debenedetti et al., NeurIPS 2024](https://arxiv.org/abs/2406.13352)），在 ASB 9 万次实测中平均 ASR 高达 84.30%（[Zhang et al., ICLR 2025](https://arxiv.org/abs/2410.02644)），且无任何模型在 Agent-SafetyBench 上得分超过 60 分（[Zhang et al., 2024](https://arxiv.org/abs/2412.14470)）。本方案以"将 ASR 降至 5-10%、Utility 保留 ≥ 80% 基线"为目标。

---

## 1. 各基准当前 SOTA 数字表

### 1.1 AgentDojo（NeurIPS 2024，ETH Zürich SPY Lab）
- **论文**：[arXiv:2406.13352](https://arxiv.org/abs/2406.13352)
- **官网/榜单**：[agentdojo.spylab.ai](https://agentdojo.spylab.ai/)
- **代码**：[github.com/ethz-spylab/agentdojo](https://github.com/ethz-spylab/agentdojo)
- **构成**：97 个真实任务 + 629 安全测试用例，覆盖 workspace / banking / slack / travel 四个工具套件

#### 模型基线（无防御，Important-Message 攻击）

| 模型 | Benign Utility | Utility Under Attack | Targeted ASR |
|---|---|---|---|
| GPT-4o | 69.00% | 50.08% | **47.69%** |
| GPT-4 Turbo | 63.43% | 54.05% | 28.62% |
| Claude 3.5 Sonnet | **78.22%** | 51.19% | 33.86% |
| Claude 3 Opus | 66.61% | 52.46% | **11.29%** |
| Gemini 1.5 Pro | 45.63% | 28.93% | 25.60% |
| Llama 3 70B | 34.50% | 18.28% | 20.03% |

来源：[arXiv:2406.13352 Table 3](https://arxiv.org/html/2406.13352)

#### 防御方案效果

| Defense | Benign Utility | UA | Targeted ASR |
|---|---|---|---|
| 无防御（baseline GPT-4o） | 69.00% | 50.08% | 47.69% |
| Data Delimiters | 72.66% | 55.64% | 41.65% |
| Prompt Sandwiching | 85.53% | 67.25% | 27.82% |
| **Tool Filter** | 73.13% | 56.28% | **6.84%** |
| Prompt-Injection Detector | utility 降到 41.49% | - | - |

来源：[arXiv:2406.13352 Table 5](https://arxiv.org/html/2406.13352)

#### 套件差异（Per-suite）
- **Slack 套件 92%** ASR（最易被注入，因为 Slack 工具常对外读取网页）
- Workspace ~45%，Banking ~35%，Travel ~15%（来源：[arXiv:2406.13352 Fig 7](https://arxiv.org/html/2406.13352)）

#### 时序进展
- AgentDojo 目标 ASR 从 GPT-4-0125 的 56.3%（2024）下降到 Claude 3.7 Sonnet 的 7.3%（2025-02），一个数量级改善。来源：[Invariant Labs](https://invariantlabs.ai/blog/agentdojo)
- 但同时新攻击崛起：US/UK AISI 的红队使 Claude 3.5 Sonnet（new）ASR 从 11% 飙升到 81%。来源：[NIST CAISI 2025-01](https://www.nist.gov/news-events/news/2025/01/technical-blog-strengthening-ai-agent-hijacking-evaluations)

---

### 1.2 Agent-SafetyBench（清华 thu-coai，2024-12）
- **论文**：[arXiv:2412.14470](https://arxiv.org/abs/2412.14470)
- **代码**：[github.com/thu-coai/Agent-SafetyBench](https://github.com/thu-coai/Agent-SafetyBench)
- **数据集**：[HuggingFace](https://huggingface.co/datasets/thu-coai/Agent-SafetyBench)
- **规模**：349 交互环境 + **2,000 测试用例**，8 类安全风险 + 10 失效模式

#### 核心结论
- 评测 16 个 LLM agent（含 Claude-3.5-Sonnet、GPT-4o、Llama-3.1、Qwen 系列等）
- **No agent achieves a safety score above 60%**（论文原文）
- 两个根本缺陷：lack of robustness（对扰动不鲁棒）+ lack of risk awareness（缺乏风险感知）
- 论文明确指出：依赖 defense prompt 单一手段不足以解决这些问题

来源：[arXiv:2412.14470 (abstract)](https://arxiv.org/abs/2412.14470)、[Semantic Scholar](https://www.semanticscholar.org/paper/Agent-SafetyBench:-Evaluating-the-Safety-of-LLM-Zhang-Cui/7d11400eeb317ebee278f49e108226a4f8555dda)

---

### 1.3 InjecAgent（UIUC, ACL 2024 Findings）
- **论文**：[arXiv:2403.02691](https://arxiv.org/abs/2403.02691) | [ACL Anthology](https://aclanthology.org/2024.findings-acl.624/)
- **代码**：[github.com/uiuc-kang-lab/InjecAgent](https://github.com/uiuc-kang-lab/InjecAgent)
- **规模**：1,054 测试用例，17 用户工具 + 62 攻击者工具

#### ReAct 范式下 ASR-valid（Table 3）

| 模型 | Direct Harm | Data Stealing S1 | Data Stealing S2 | 总 ASR (基础) | 总 ASR (加 hacking prompt) |
|---|---|---|---|---|---|
| GPT-4 (Prompted) | 14.7% | 32.7% | **97.7%** | 23.6% | **47.0%** |
| GPT-3.5 (Prompted) | 18.8% | 37.6% | 77.4% | 23.7% | 39.8% |
| Claude-2 (Prompted) | 7.5% | 26.5% | 58.1% | 11.4% | 3.4% |
| Llama2-70B (Prompted) | 91.9% | 97.1% | 83.7% | **86.9%** | 88.2% |
| GPT-4 (Fine-tuned) | 2.9% | 10.1% | **100%** | 6.6% | 7.1% |
| GPT-3.5 (Fine-tuned) | 1.8% | 5.7% | **100%** | 3.8% | 8.4% |

**关键洞见**：数据外泄（S2 transmission）几乎 100% 成功——一旦数据被提取出来，模型几乎不会拒绝把数据转发出去。这是政企场景最致命的攻击面。来源：[arXiv:2403.02691v3](https://arxiv.org/html/2403.02691v3)

---

### 1.4 AIR-Bench 2024（Stanford CRFM）
- **论文**：[arXiv:2407.17436](https://arxiv.org/abs/2407.17436)
- **代码/榜单**：[github.com/stanford-crfm/air-bench-2024](https://github.com/stanford-crfm/air-bench-2024)
- **规模**：**5,694 个 prompt**，覆盖 314 个细粒度风险类别，基于 8 个政府监管 + 16 家公司政策
- **特色**：第一个与监管/政策对齐的 AI 安全基准（含中国监管要素）

#### Top Refusal Rate（22 模型，5,694 prompts）

| 模型 | 平均 Refusal Rate |
|---|---|
| **Claude 3 Sonnet** | **89%** |
| Claude 3 Haiku | 89% |
| Claude 3 Opus | top tier |
| Gemini 1.5 Pro | 第二梯队 |
| GPT-4o / GPT-4 Turbo | 中等 |
| Llama 3 70B / Mixtral 8x22B | 中等 |
| **DBRX Instruct** | **15%**（约 85% 给出潜在有害内容） |

注意：即便是最强的 Claude 3 Sonnet 在 #4 Automated Decision-Making 类别也只有 70% 拒绝率，存在系统性盲区。来源：[arXiv:2407.17436v2](https://arxiv.org/html/2407.17436v2)

---

### 1.5 R-Judge（SJTU, EMNLP 2024 Findings）
- **论文**：[arXiv:2401.10019](https://arxiv.org/abs/2401.10019) | [ACL Anthology](https://aclanthology.org/2024.findings-emnlp.79/)
- **代码**：[github.com/Lordog/R-Judge](https://github.com/Lordog/R-Judge)
- **规模 (v3)**：569 多轮交互记录，27 关键风险场景，5 应用类别，10 风险类型
- **任务**：判别给定的 agent 交互轨迹是否存在安全风险（F1 + Recall + Specificity）

#### 主要结果
- 最佳模型 **GPT-4o：74.42% F1**
- 大部分模型未显著超过 random baseline
- 早期 v1 中 GPT-4 取得 72.29%，人类基线 89.38%

意义：风险识别能力是政企场景"事中检测"的必备能力，目前 SOTA 也远未达到人类水平。来源：[arXiv:2401.10019](https://arxiv.org/abs/2401.10019)

---

### 1.6 ToolEmu（ICLR 2024 Spotlight, U. Toronto + UIUC）
- **论文**：[arXiv:2309.15817](https://arxiv.org/abs/2309.15817) | [OpenReview](https://openreview.net/forum?id=GEcwtMk1uA)
- **代码**：[github.com/ryoungj/toolemu](https://github.com/ryoungj/toolemu)
- **规模**：36 工具包（311 工具）+ 144 测试用例
- **方法**：用 LLM 模拟工具执行（不需要真实 API），自动生成失效场景

#### 关键数字
- **最安全的 LM agent 仍然有 23.9% 的失效率**（severity-weighted failure rate）
- 人工验证：68.8% 的失效是真实合法的（不是模拟器幻觉）
- 失效模式：fabrication、unwarranted assumptions、instruction misinterpretation、erroneous execution、risk ignorance

23.9% 数字的意义：即使是良性用户 + 良性意图，无任何攻击，最优 agent 在工具调用场景下仍有近 1/4 概率造成严重后果。这是设定"non-adversarial baseline"的关键数字。来源：[arXiv:2309.15817](https://arxiv.org/abs/2309.15817)

---

### 1.7 Agent Security Bench / ASB（Rutgers + ZJU, ICLR 2025）
- **论文**：[arXiv:2410.02644](https://arxiv.org/abs/2410.02644)
- **代码**：[github.com/agiresearch/ASB](https://github.com/agiresearch/ASB)
- **规模**：10 场景 + 10 agent + **400+ 工具** + 23 种攻击/防御方法 + 8 评测指标，接近 **90,000 episodes**
- **新指标**：Net Resilient Performance (NRP) = PNA × (1 − ASR)

#### 攻击类别 ASR（13 LLM 平均，Table 5）

| 攻击 | 平均 ASR |
|---|---|
| **Mixed Attack**（DPI+IPI+Memory Poisoning 组合） | **84.30%**（最高） |
| Direct Prompt Injection (DPI) | ~71% |
| Plan-of-Thought (PoT) Backdoor | ~42%（GPT-4o 高达 **100%**，GPT-4o-mini 95.5%） |
| Plan-of-Thought 平均 | ~32% |
| Indirect Prompt Injection (IPI) | ~24% |
| Memory Poisoning | ~8% |

关键发现：
- 越强的模型可能更易被复杂后门攻击（GPT-4o 在 PoT 后门下 100% 中招）
- Mixed Attack 拒绝率仅 3.22%
- 现有防御方法效果有限（论文原文：limited effectiveness shown in current defenses）

来源：[arXiv:2410.02644 (v3 ICLR 2025)](https://arxiv.org/html/2410.02644v3)

---

### 1.8 HarmBench（CAIS, ICML 2024）
- **论文**：[arXiv:2402.04249](https://arxiv.org/abs/2402.04249)
- **代码**：[github.com/centerforaisafety/HarmBench](https://github.com/centerforaisafety/HarmBench)
- **规模**：18 红队方法 × 33 目标 LLM/防御
- **方法**：自动化红队 + 鲁棒拒绝评测的标准化框架
- **核心贡献**：除了基准，还提出了一种高效的对抗训练方法显著提升 LLM 鲁棒性

HarmBench 是红队能力评测的事实标准——评委会大概率拿它来"复测我们"。来源：[arXiv:2402.04249](https://arxiv.org/abs/2402.04249)

---

## 2. 业界防御方案 ASR 改善幅度（关键参考）

| 防御方案 | 基础 ASR | 加防御后 ASR | 备注 |
|---|---|---|---|
| **AgentDojo: Tool Filter** | 47.69% (GPT-4o) | **6.84%** | 但 Utility 也降到 56.28% |
| **AgentDojo: Prompt Sandwiching** | 47.69% | 27.82% | Utility 67.25%（最佳工具/效益平衡） |
| **AgentDojo: Data Delimiters** | 47.69% | 41.65% | 改善有限 |
| **StruQ**（结构化查询） | ~96%（Sandwich baseline） | ~45% | 对优化攻击仍 34-62% 失败 |
| **SecAlign**（preference opt.） | ~96% | **<10%** | 部分场景接近 0%，但需要训练模型 |
| **Meta SecAlign** | 53.8%（InjecAgent） | **0.5%** | 训练级防御，开源 70B 模型 |
| **CaMeL**（Google DeepMind） | - | 防御 67% 的注入攻击 | 但 Utility 84% / 77%；推理 token 增 2.7-2.8 倍 |
| **PromptArmor** | 47%-56% | **0-0.47% ASR** | UA 仍 72-76%（守护 LLM 检测注入） |

来源：
- [SecAlign arXiv:2410.05451](https://arxiv.org/abs/2410.05451)
- [Berkeley BAIR Blog 2025-04](https://bair.berkeley.edu/blog/2025/04/11/prompt-injection-defense/)
- [Meta SecAlign arXiv:2507.02735](https://arxiv.org/abs/2507.02735)
- [CaMeL arXiv:2503.18813](https://arxiv.org/abs/2503.18813)
- [InfoQ on CaMeL](https://www.infoq.com/news/2025/04/deepmind-camel-promt-injection/)

### 业界 ASR 改善的"光谱"
- **弱**（提示词级别防御）：ASR 降到 25-40%
- **中**（结构化 + 检测器组合）：ASR 降到 10-20%
- **强**（训练级 / 架构级）：ASR 降到 1-7%
- **理想但有代价**（CaMeL / PromptArmor）：ASR 接近 0%，但 Utility 损失 5-15% 或 token 翻倍

---

## 3. 给我们项目的合理目标设定（核心建议）

### 3.1 ASR 改善目标（三档）

| 档位 | 建议数字 | 业界对标 | 风险 |
|---|---|---|---|
| **保底**（写在 PRD 必达） | ASR **从 ~50% 降至 ≤ 20%** | AgentDojo Sandwich (27.82%) / StruQ (45%) | 评委不会质疑 |
| **中等**（主推论调） | ASR **从 ~50% 降至 ≤ 10%** | SecAlign (<10%) / AgentDojo Tool Filter (6.84%) | 业界优秀水平 |
| **前沿**（标 limitation） | ASR **降至 ≤ 5%**，并明确"仍存在 adaptive attack 残余风险" | CaMeL (67% 防御率) / PromptArmor (0-0.47%) | 不可承诺零 ASR，否则评委必问 |

**建议主基线写法**：

> 在 AgentDojo / InjecAgent / 自建中文政企基准上，将 Targeted ASR 从无防御基线（~30-50%）降至 ≤ 8-10%，同时保留 ≥ 80% 的 Utility。

### 3.2 Utility 保留目标

AgentDojo 数据显示：
- 最佳无防御模型 Benign Utility = 78.22%（Claude 3.5 Sonnet）
- 加防御后 Utility 通常掉 5-15 个百分点
- AgentDojo Prompt Sandwiching 是少数能让 Utility 提升到 85.53% 的方案

建议 PRD 目标：
- **Benign Utility 保留 ≥ 90% of baseline**（即如 baseline 78%，加防御后 ≥ 70%）
- **Attack-time Utility ≥ 50%**（业界普通水平）
- 明确说"防御不会让任务完成率掉超过 15 个百分点"

### 3.3 测评数据集规模（200-300 用例评估）

| 基准 | 用例数 | 评论 |
|---|---|---|
| Agent-SafetyBench | 2,000 | 中等偏大 |
| AgentDojo | 629 安全用例 | 中等 |
| InjecAgent | 1,054 | 中等 |
| AIR-Bench 2024 | 5,694 | 大 |
| ToolEmu | 144 | 小 |
| R-Judge | 569 | 中等 |
| ASB | 90,000 episodes | 实测规模 |

**结论：200-300 用例处于"偏小但合理"范围**：
- 与 ToolEmu（144）和早期 R-Judge v1（162）同档
- 但显著小于 Agent-SafetyBench（2000）、InjecAgent（1054）、AgentDojo（629）
- **建议**：PRD 中 200-300 用例可以保，但要明确"作为政企中文场景的初始 PoC，规划下一阶段扩展到 800-1000 用例"，避免被评委追问"为什么这么少"
- 推荐目标：**第一期 300 用例**（覆盖 8-10 类风险），论证可扩展至 1000+

### 3.4 评委会可能用什么基准考我们？

按"易复测 + 中文相关 + 政企对口"排序，雄安专家最可能引用的基准：

1. **CHiSafetyBench**（[arXiv:2406.10311](https://arxiv.org/abs/2406.10311)） —— 直接对齐 TC260《生成式人工智能服务基本安全要求》，5 大领域 + 31 子类。**必备**。
   - 中国联通已用它评测 40+ 开源模型（[AI for Good](https://aiforgood.itu.int/enhancing-open-source-large-language-models-for-industrial-use-insights-from-china-unicom/)）
2. **Agent-SafetyBench**（清华出品，2000 用例 + agent 场景，国内引用率高）
3. **AgentDojo**（最广为人知的 agent 注入基准；US/UK AISI 在用）
4. **InjecAgent**（数据外泄场景特别贴合政企）
5. **HarmBench**（红队评测事实标准）
6. **R-Judge**（上交大，国内）—— 风险判别能力，对应"事中防御"的能力

**强烈建议**：PRD 至少声明"在 AgentDojo + InjecAgent + CHiSafetyBench + 自建中文政企基准（300 用例）"四个 benchmark 上做评测，覆盖英文学术 + 中文监管 + 工具注入 + 数据外泄四个维度。

---

## 4. 政企场景特殊评测维度（区别于学术基准）

学术基准未充分覆盖的政企特殊维度，是我们方案的差异化卖点：

### 4.1 中文场景特殊性
- **CHiSafetyBench**：唯一对齐 TC260 标准的基准。覆盖"歧视 / 违反核心价值观 / 商业违规 / 侵犯权益 / 特定服务安全"5 类
- **CSSBench**（[arXiv:2601.00588](https://arxiv.org/abs/2601.00588)）：中文特有对抗模式（拼音、形近字、繁体替换、零宽字符）
- **Chinese SafetyQA**（[arXiv:2412.15265](https://arxiv.org/abs/2412.15265)）：中国法律 / 政策 / 主流价值的安全事实性
- **我们的差异化**：现有中文基准没有 agent 工具调用场景的中文数据，是真空地带

### 4.2 政企合规要求（无现成基准）
- 数据出境管控 / 个保法 / 数据安全法（《关键信息基础设施安全保护条例》）
- 行业准入资质（金融、医疗、政务）
- 国密算法对接
- 等保 2.0 / 三级等保审计要求

### 4.3 跨工具链编排风险
- **AgentDojo 的 Slack 套件 92% ASR** 印证：跨工具调用是最脆弱环节
- InjecAgent 的 S2 数据外泄 97-100% ASR：一旦数据被读出，模型几乎不拒绝转发
- 政企场景的工具链更长（OA -> 邮件 -> 文件系统 -> 外网），风险倍增
- 建议引入"跨工具流转的可审计性 + capability-based 访问控制"（参考 CaMeL 的 dual-LLM + capability tagging）

### 4.4 评测维度推荐组合

PRD 建议在如下 4 维度评测（每维有量化目标）：

| 维度 | 推荐指标 | 目标基线 |
|---|---|---|
| **抗注入鲁棒性** | Targeted ASR @ AgentDojo / InjecAgent | ≤ 10% |
| **任务完成率** | Benign Utility / Attack-time Utility | ≥ 80% / ≥ 50% |
| **风险识别** | F1 @ R-Judge / 自建检测集 | ≥ 75%（GPT-4o 是 74.42%） |
| **合规对齐** | Refusal Rate @ CHiSafetyBench + 自建政企集 | ≥ 85%（Claude 3 Sonnet 是 89%） |

---

## 5. 总结建议（PRD 直接抄写段落）

> ### 评测目标设定
>
> 本方案的安全防护效果将在以下基准上验证，目标基线综合参考 2024-2026 年学术 SOTA：
>
> 1. **抗 Prompt 注入**：在 AgentDojo（[Debenedetti et al., NeurIPS 2024](https://arxiv.org/abs/2406.13352)）的 629 安全用例上，将 Targeted ASR 从无防御基线（GPT-4o: 47.69%）降至 ≤ 10%，对标业界 SOTA 的 SecAlign（< 10% ASR, [arXiv:2410.05451](https://arxiv.org/abs/2410.05451)）与 AgentDojo Tool Filter（6.84%）。
> 2. **抗间接注入与数据外泄**：在 InjecAgent（[Zhan et al., ACL 2024](https://arxiv.org/abs/2403.02691)）的 1054 用例上，将总 ASR-valid 从 ~24% 降至 ≤ 5%，重点压制数据外泄（S2）的 97-100% 高危场景。
> 3. **任务效用保持**：Benign Utility 保留 ≥ baseline 的 90%，攻击下 Utility ≥ 50%。
> 4. **风险识别**：在 R-Judge（[Yuan et al., EMNLP 2024](https://arxiv.org/abs/2401.10019)）上 F1 ≥ 75%（GPT-4o 当前 SOTA 为 74.42%）。
> 5. **中文政企合规**：在 CHiSafetyBench（[arXiv:2406.10311](https://arxiv.org/abs/2406.10311)，对齐 TC260 标准）上 Refusal Rate ≥ 85%；并在自建 300 用例中文政企基准上达到同等水平。
>
> **Limitation 声明**：所有数字均存在 adaptive attack 残余风险。Agent-SafetyBench（[arXiv:2412.14470](https://arxiv.org/abs/2412.14470)）的研究表明，目前没有任何 LLM agent 安全分能突破 60 分；ASB（[arXiv:2410.02644](https://arxiv.org/abs/2410.02644)）的 9 万次实测显示，Mixed Attack 平均 ASR 高达 84.30%。本方案不承诺零 ASR，但承诺将平均 ASR 推到业界优秀防御方案的水平区间（5-10%），并保留可扩展的对抗演化能力。

---

## 附录：所有引用 URL 速查

### 学术论文
- AgentDojo: https://arxiv.org/abs/2406.13352
- Agent-SafetyBench: https://arxiv.org/abs/2412.14470
- InjecAgent: https://arxiv.org/abs/2403.02691
- AIR-Bench 2024: https://arxiv.org/abs/2407.17436
- R-Judge: https://arxiv.org/abs/2401.10019
- ToolEmu: https://arxiv.org/abs/2309.15817
- ASB: https://arxiv.org/abs/2410.02644
- HarmBench: https://arxiv.org/abs/2402.04249
- SecAlign: https://arxiv.org/abs/2410.05451
- Meta SecAlign: https://arxiv.org/abs/2507.02735
- CaMeL: https://arxiv.org/abs/2503.18813
- CHiSafetyBench: https://arxiv.org/abs/2406.10311
- CSSBench: https://arxiv.org/abs/2601.00588
- Chinese SafetyQA: https://arxiv.org/abs/2412.15265

### 代码 / 数据
- AgentDojo: https://github.com/ethz-spylab/agentdojo
- Agent-SafetyBench: https://github.com/thu-coai/Agent-SafetyBench
- InjecAgent: https://github.com/uiuc-kang-lab/InjecAgent
- AIR-Bench: https://github.com/stanford-crfm/air-bench-2024
- R-Judge: https://github.com/Lordog/R-Judge
- ToolEmu: https://github.com/ryoungj/toolemu
- ASB: https://github.com/agiresearch/ASB
- HarmBench: https://github.com/centerforaisafety/HarmBench
- CaMeL: https://github.com/google-research/camel-prompt-injection

### 行业分析
- NIST CAISI on Claude 3.5 Sonnet (2025-01): https://www.nist.gov/news-events/news/2025/01/technical-blog-strengthening-ai-agent-hijacking-evaluations
- Berkeley BAIR Blog on SecAlign (2025-04): https://bair.berkeley.edu/blog/2025/04/11/prompt-injection-defense/
- Invariant Labs AgentDojo: https://invariantlabs.ai/blog/agentdojo
- China Unicom 政企 LLM 安全实践: https://aiforgood.itu.int/enhancing-open-source-large-language-models-for-industrial-use-insights-from-china-unicom/

---

**调研完成时间**：2026-05-23
**字数**：约 3300 字（不含表格与代码段）
