# 综述：RAG 安全的攻击与防御分类法 (Securing Retrieval-Augmented Generation: A Taxonomy of Attacks, Defenses, and Future Directions)

## 元信息
- **作者机构**: The Hong Kong Polytechnic University + HKUST (Yuming Xu 等)
- **年份 · 发表**: 2026-04 · arXiv (2026 最新综述)
- **arXiv**: https://arxiv.org/abs/2604.08304
- **本地 PDF**: ./2026-AdvRAGSurvey.pdf
- **代码**: 无（综述论文）
- **难度**: 2/5

## 一句话总结
2026 年最新的 RAG 安全综述：把 RAG 工作流分成 6 阶段，围绕 3 条信任边界和 4 大安全面，系统梳理所有已知攻击与防御。

## 解决什么问题
RAG 安全在 2024-2025 年井喷式发展（PoisonedRAG、RobustRAG、TrustRAG、Traceback-RAG 等），但**问题是论文太多、分散、定义不一**：
- 不同工作的"威胁模型"定义不一致
- "RAG 引入的新风险" vs "LLM 本身固有风险" 边界模糊
- 防御方案各做各的，缺乏整体框架

这篇综述想做的事：**建立一个清晰的 taxonomy**，让研究者和工程师能：
1. 快速找到自己关心的攻击/防御类别
2. 理解每个方向的研究现状
3. 识别未来研究空白

对我们这种"快速理解领域全貌"的学生团队特别有用。

## 用了什么方法（综述的结构）
**核心打比方**：之前所有 RAG 安全研究像一堆杂乱的菜，这篇论文像一本"菜谱总目录"，按"菜系（攻击/防御）× 难度（阶段）× 类别（信任边界）"做了完整分类。

**核心框架**：

### RAG 工作流的 6 个阶段
1. Data Collection（数据收集）
2. Indexing（索引建立）
3. Query Embedding（查询编码）
4. Retrieval（检索）
5. Reranking（重排）
6. Generation（生成）

### 3 条信任边界
- **External corpus boundary**（外部语料库 vs 内部）
- **Retrieval-time access boundary**（检索时的访问控制）
- **Output disclosure boundary**（输出披露的限制）

### 4 个主要安全面
1. **Pre-retrieval Knowledge Corruption**（检索前知识投毒）—— PoisonedRAG 类
2. **Retrieval-time Access Manipulation**（检索时访问操纵）—— 操纵 retriever 行为
3. **Downstream Context Exploitation**（下游上下文利用）—— 间接 prompt injection
4. **Knowledge Exfiltration**（知识窃取）—— 通过查询反推知识库内容

**综述结论（重点）**：
- 现有防御**大多反应式、碎片化**：每个工作针对一种攻击设计一种方案
- 未来需要**分层、边界感知**的整体防护框架
- 评测基准不一致是大问题——不同论文用不同数据集，难以横向对比

**与具体研究论文的区别**：
- 不是新方法，而是"地图"——帮你快速定位自己在哪里
- 引用文献覆盖到 2026 年（含最新工作）
- 同时关注 attacks + defenses + benchmarks（其他综述往往只关注一面）

## 为什么能解决
（综述类论文不解决具体技术问题，主要解决"认知/规划"问题）

价值：
1. 帮新人快速建立领域全景
2. 帮研究者定位空白
3. 帮工程师选择适合自己场景的防御方案

**何时不太有用**：
1. 你已经是 RAG 安全专家了——这种综述对你来说太"入门"
2. 你只关心 1-2 篇具体方法的细节——直接看原论文更好

## 主要结果（综述贡献）
- 提出**统一的 6 阶段 + 3 边界 + 4 安全面**分类框架
- 系统梳理 ~150+ 篇相关论文
- 指出 5 大未来研究方向：
  1. Layered, boundary-aware defenses
  2. Unified RAG security benchmarks
  3. RAG-specific forensics tools
  4. Privacy-preserving retrieval
  5. Agentic RAG security (涉及多 agent 协同时的复合风险)

## 局限性
1. 综述类论文不可避免会**滞后**（截至 2026-04，后续新工作未覆盖）
2. 分类框架可能过于宽泛，对具体方法细节较少
3. 对中文/政企场景的特殊性几乎未涉及

## 我们项目里的用法
**对应关卡**：方向 1 整体（不限于 RAG）的认知地图，**全员阅读建议**。
- **核心用法**：作为**方向 1 整体阅读的"目录页"**，让组员快速找到自己关心的细分领域
- **架构图借鉴**：综述的 6 阶段 × 4 安全面框架可以**直接搬到我们方案文档**中，作为"我们的 RAG 防御架构覆盖哪些安全面"的说明依据
- **空白填充**：综述指出的 5 个未来方向是**我们方案差异化的指引**——我们重点做的"分层防御 + forensics + 中文政企基准"恰好覆盖了 1、3 两个空白
- **答辩材料**：作为权威背书，证明我们方案的设计是"踩在最新综述指出的方向上"

## 学习路径
- **5 分钟版**：看 Figure 1（整体分类框架图）+ Section 6 Future Directions
- **30 分钟版**：通读 Section 2-4（taxonomy 与各安全面）
- **作为目录**：根据自己关心的话题（如"投毒攻击"、"防御方法"），快速跳转到对应章节
- **跳过**：可以略过不太相关的子领域细节
- **关键图**：Figure 1（综述分类总图）
- **配套阅读**：综述读完后，挑 2-3 个你最关心的方向去读原论文（如 PoisonedRAG、TrustRAG、Traceback-RAG）
