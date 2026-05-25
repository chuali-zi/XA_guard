# RAGPart & RAGMask: 在检索器阶段做 RAG 防御 (RAGPart & RAGMask: Retrieval-Stage Defenses Against Corpus Poisoning in RAG)

## 元信息
- **作者机构**: University of Maryland College Park + Capital One + Peraton Labs (Pankayaraj Pathmanathan, Furong Huang 等)
- **年份 · 发表**: 2025-12 · arXiv (2025 末新论文)
- **arXiv**: https://arxiv.org/abs/2512.24268
- **本地 PDF**: ./2025-RAGPart.pdf
- **代码**: 论文中提到未来开源
- **难度**: 3/5

## 一句话总结
不在生成阶段防御，**在检索阶段就拦住恶意文档**：两种方法——RAGPart 利用 retriever 训练动态、RAGMask 用 token mask 找可疑文档。

## 解决什么问题
之前所有的 RAG 防御方案（RobustRAG / TrustRAG）都聚焦在"生成阶段"——文档已经被检索回来了，再做过滤或聚合。这有两个问题：
1. **计算浪费**：恶意文档已经被 embedding 编码 + 排序，再删掉浪费算力
2. **延迟累积**：生成阶段加防御 = LLM 调用次数增加，推理慢

RAGPart 的洞察：**很多攻击文档与正常文档的"行为特征"在检索阶段就有差异**——比如恶意文档对 retriever 的某些 token 异常敏感、与训练数据的相似度模式异常。如果在检索阶段就用这些信号过滤，效率和效果都更好。

## 用了什么方法
**核心打比方**：
- 之前的方案：商品到了仓库后再质检（昂贵）
- RAGPart：在入库的传送带上就装异常检测器（更快、更便宜）

**两种互补方法**：

### RAGPart：利用 Retriever 训练动态
1. **观察**：dense retriever（如 BGE、Contriever）训练时见过的"正常文档分布"已经被编码进权重
2. **方法**：把 corpus 分成几个不重叠的 partition，分别用**不同子集训练的 retriever**做检索；对同一 query，不同 retriever 给出不同 ranking
3. **关键洞察**：恶意文档通常**对 retriever 选择极其敏感**——换一个 retriever 排名急剧变化；而正常文档排名稳定
4. 用排名稳定性作为"是否是恶意文档"的信号

### RAGMask：利用 Token Mask 测敏感性
1. **观察**：攻击者为了让文档被检索，会精心构造关键 token（如目标问题的关键词）；这些 token 的存在对相似度贡献极大
2. **方法**：对每个候选文档，逐个 mask 掉某个 token 后重新计算与 query 的相似度
3. **关键洞察**：恶意文档**少数关键 token 决定整体相似度**——mask 掉它，相似度断崖式下跌；正常文档对单个 token 鲁棒（信息分散）
4. 检测"敏感性异常高"的文档作为可疑

**两种方法可叠加**：先用 RAGPart 做粗筛（基于多 retriever 排名），再用 RAGMask 做精筛（基于 token 敏感性）。

**与之前方法的区别**：
- vs RobustRAG / TrustRAG：发生在更早的阶段（检索 vs 生成）
- vs 重训 retriever：RAGPart/RAGMask 不需要重训，复用现有 retriever
- vs 关键词过滤：用 retriever 内部信号，比表层关键词鲁棒

## 为什么能解决
关键直觉：**攻击文档为了同时满足"被检索"+"误导 LLM"两个目标，往往呈现某些异常签名**——比如对 retriever 高度敏感（RAGMask 可测）、与训练分布偏离（RAGPart 可测）。这些签名在检索阶段就可观察，无需走到生成阶段。

**何时会失效**：
1. 攻击者构造**对多 retriever 鲁棒**的文档（成本高但可能）
2. 攻击者用"信息分散"策略（不依赖少数关键 token）
3. 与 corpus 中正常文档高度相似的攻击文档（如改写真实文档）

## 主要结果
- 在两个基准 + 四种攻击策略 + 四种 retriever 的组合上验证
- 对 PoisonedRAG 等主流攻击的 ASR **稳定降低 40-70%**
- 不需要额外训练，仅在推理阶段加滤镜
- 推理延迟增加 < 20%（远低于 RobustRAG 的 N 倍）
- 在 benign（无攻击）情况下 utility 损失 < 3%

## 局限性
1. 对**自适应攻击**（攻击者了解 RAGPart/RAGMask 后定制攻击）效果待观察
2. RAGPart 需要维护多个 retriever 副本，存储成本上升
3. RAGMask 的 token mask 计算可能较慢（每个文档 N 次 query）
4. 论文较新（2025-12），社区尚未完全验证

## 我们项目里的用法
**对应关卡**：第 3 关「RAG 防污染」的**检索阶段补充层**。
- **架构融合**：构建多层防御 —— 检索阶段用 RAGMask（计算便宜）做粗筛 → 生成阶段用 TrustRAG 双滤做精筛
- **学术亮点**：方案里可以提到我们采用了 **"检索 + 生成双阶段"** 的纵深 RAG 防御，相比单点防御更鲁棒
- **轻量实现**：RAGMask 实现非常简单（< 100 行代码），可作为我们方案的核心创新点之一
- **演示**：在 demo 里可以可视化"被 RAGMask 标记的可疑文档"，给评委看具体过滤效果

## 学习路径
- **5 分钟版**：看 Figure 1 + Figure 2（两种方法示意图）+ Table 1 主结果
- **30 分钟版**：Section 2「RAGPart」+ Section 3「RAGMask」+ Section 4 实验
- **跳过**：附录的进阶分析可以选读
- **关键图**：Figure 2（token mask 工作流）、Table 3（多攻击多 retriever 的 ASR 矩阵）
- **配套阅读**：先看 PoisonedRAG → TrustRAG → 本文（按时间顺序看 RAG 防御演进）
