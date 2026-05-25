# Traceback-RAG: 投毒攻击的事后溯源 (Traceback of Poisoning Attacks to Retrieval-Augmented Generation)

## 元信息
- **作者机构**: Nankai University + University of Louisville + University of North Texas (Baolei Zhang, Minghong Fang 等)
- **年份 · 发表**: 2025-04 · arXiv
- **arXiv**: https://arxiv.org/abs/2504.21668
- **本地 PDF**: ./2025-TracebackRAG.pdf
- **代码**: 见论文 GitHub 仓库链接
- **难度**: 3/5

## 一句话总结
当 RAG 系统出错了，怎么**定位**究竟是哪几篇文档把它带偏了？这是 RAG 安全的"事故调查"环节——为审计、追责、修复提供证据。

## 解决什么问题
之前所有 RAG 安全工作都聚焦在 **prevention（预防）**——如何在攻击发生前/中拦住它。但安全管理一定是闭环的：
1. **Prevention**（预防）：PromptGuard / TrustRAG / RobustRAG
2. **Detection**（检测）：发现出错了
3. **Forensics**（取证/溯源）：定位是哪些文档导致的
4. **Response**（响应）：从知识库清除并修复
5. **Audit**（审计）：留下证据链供监管核查

**Forensics 这一环节几乎是空白的**。当一个 RAG 客服回答错了客户问题，运维想知道"为什么错了？是哪篇文档导致的？谁上传的？什么时候上传的？"。这是事后审计、合规追责、模型修复的关键。

Traceback-RAG 是**业界首个 RAG 投毒攻击溯源框架**。

## 用了什么方法
**核心打比方**：当一个证人在法庭上做了伪证导致错判，法医不是把案件重审一遍（成本高），而是从"伪证的话语风格、与其他证人陈述的矛盾点、证人来源"等线索反推出谁说了假话。Traceback-RAG 做的就是这种"反推"。

**核心两步**：

### 第一步：影响力归因 (Influence Attribution)
- 对每个 retrieved 文档，估计它对最终错误回答的"贡献度"
- 方法可以是：
  - **Leave-one-out**：移除该文档后重新生成，看回答变化（精确但贵）
  - **Gradient-based**：用 LLM 的梯度估计每个文档的影响（快但要白盒）
  - **Attention-based**：分析 cross-attention 权重（折中）
- 输出：每个文档的"嫌疑值"

### 第二步：聚类与定位 (Cluster & Identify)
- 把"高嫌疑值"的文档聚类
- 同一攻击批次的恶意文档通常聚集（语义近、来源同）
- 输出溯源报告：哪批文档、来源 (uploader/timestamp)、攻击模式

**关键创新**：
- 把 RAG 中的"文档级影响力归因"形式化为一个数学问题
- 给出实用的近似算法（不必每次都做 leave-one-out）
- 集成到 RAG pipeline 形成完整 forensics 链

**与之前方法的区别**：
- 之前的 RAG 防御都是 prevention/detection 端
- Traceback-RAG 是**唯一**专注 forensics 的工作
- 与方向 4（审计溯源）天然衔接

## 为什么能解决
关键直觉：**LLM 的回答是其检索到的文档的函数**。理论上对每个文档做扰动，观察输出变化，就能恢复出"哪些文档贡献了错误回答"。这与软件 bug 的 bisect 调试同理。

**何时会失效**：
1. 攻击者用大量低影响小文档累积影响（"千刀万剐"式）—— 单个文档影响力都低，难定位
2. 当 LLM 自身有 bias 导致错误时，归因可能误指文档
3. 多轮对话中错误回答受多轮上下文影响，难定位到单一文档

## 主要结果
- 在 NQ / TriviaQA 等数据集 + PoisonedRAG 攻击下：
  - 恶意文档**定位准确率 > 85%**（Top-K 中正确包含真实恶意文档）
  - 误报率 (FPR) < 10%
- 计算成本：可控（gradient-based 加速版接近实时）
- 兼容 GPT-4 / Llama / Mistral

## 局限性
1. 对**自适应攻击者**（知道你在做溯源，主动隐藏踪迹）效果待观察
2. 需要保留检索历史（存储成本上升）
3. Gradient-based 方法对闭源 API 模型不可用

## 我们项目里的用法
**对应关卡**：第 3 关「RAG 防污染」+ 第 7 关「审计溯源」的桥梁。
- **核心借鉴**：我们方案的方向 4 审计模块要做"溯源报告"，Traceback-RAG 是**直接可借鉴的算法基础**
- **集成场景**：当我们的运维助手出错了（用户反馈或自动检测），自动启动 Traceback 流程，定位是哪些文档、什么时间、谁上传的——形成审计报告
- **演示价值**：在 demo 中演示一次"投毒攻击 → 检测 → 溯源 → 修复"完整闭环，给评委看完整的安全运营能力，比单点防御加分
- **学术亮点**：在方案中明确提到"我们的方案不仅 prevention 还包括 forensics，借鉴 Traceback-RAG"，这是个差异化亮点
- **结合方向 4 审计**：所有 Traceback 报告上链（国密 SM3 哈希链），形成不可篡改证据

## 学习路径
- **5 分钟版**：Section 1 + Figure 1（溯源 pipeline）+ Table 2 主结果
- **30 分钟版**：Section 3「Method」+ Section 4 实验
- **跳过**：可以略过具体梯度计算的数学细节
- **关键图**：Figure 1（forensics 流程）、Figure 4（影响力分布可视化）
- **配套阅读**：先看 PoisonedRAG（攻击）+ TrustRAG（预防）+ 本文（溯源），形成 RAG 安全完整闭环认知
