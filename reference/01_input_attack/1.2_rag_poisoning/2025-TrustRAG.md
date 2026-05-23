# TrustRAG: 双阶段过滤实现 RAG 鲁棒化 (TrustRAG: Enhancing Robustness and Trustworthiness in Retrieval-Augmented Generation)

## 元信息
- **作者机构**: Imperial College London + Peking University + UNC + UCL (Huichi Zhou 等)
- **年份 · 发表**: 2025 · arXiv (2025 SOTA)
- **arXiv**: https://arxiv.org/abs/2501.00879
- **本地 PDF**: ./2025-TrustRAG.pdf
- **代码**: https://github.com/HuichiZhou/TrustRAG
- **难度**: 3/5

## 一句话总结
两阶段防御：先用**聚类**过滤掉可疑文档群，再让 **LLM 自评估**剔除剩余可疑文档；即插即用、训练无关、性能优秀。

## 解决什么问题
RAG 投毒在 2024 年成为热点话题后，业界给出了一系列防御方案：
- **RobustRAG**：可证明鲁棒，但 N 倍成本，关键词聚合损失流畅度
- **ASTUTE RAG**：靠 prompt engineering 让模型自我审查，但攻击者污染文档数量超过干净文档时失效
- **InstructRAG**：teacher-student 训练，需要重新训练模型

**所有这些方法都有一个共性问题：当攻击者注入大量恶意文档（甚至超过干净文档），现有方案普遍失效**。例如 PoisonedRAG 注入 5 篇时大部分防御还行，注入 20 篇时多数防御崩了。

TrustRAG 想做：**对抗大规模投毒，仍能保持高鲁棒性**，且不需要重训。

## 用了什么方法
**核心打比方**：警察找内奸，先按"行为相似度"把人分成几个小团伙（聚类），可疑团伙整体排查；剩下散户再让"内审 LLM"逐个面试，问出"自己说话有没有自相矛盾"。

**两阶段防御**：

**阶段 1：聚类过滤 (Cluster Filtering)**
- 把检索到的 K 篇文档做 embedding 后跑 K-Means 聚类
- 攻击者注入的恶意文档通常**互相高度相似**（同一攻击模板生成），会聚成一个紧密的小簇
- 检测"异常紧密"的簇（簇内方差远小于其他簇）并整体丢弃
- 这一步能批量清理"模板化攻击"

**阶段 2：LLM 自评估 (Self-Assessment)**
- 把剩余文档配对让 LLM 比较："这两篇文档相互一致吗？哪一篇更可信？"
- LLM 利用内部参数化知识 + 文档间互证关系剔除剩余可疑文档
- 这一步能清理"看似合理但事实错误"的高质量伪造文档

**最后**：把过滤后的可信文档喂给 LLM 生成答案。

**关键创新**：
- 完全 **plug-and-play**：在现有 RAG pipeline 上加两个滤镜，不动 retriever 也不动 generator
- **训练无关**：不需要重训任何模型
- 可与任何 LLM (闭源 GPT-4 / 开源 Llama) 组合

**与之前方法的区别**：
- vs RobustRAG：TrustRAG 是过滤式（删除可疑），RobustRAG 是聚合式（保留并稀释）
- vs ASTUTE：TrustRAG 显式利用聚类信号，比纯 prompt engineering 更鲁棒
- vs InstructRAG：无需训练，部署成本低

## 为什么能解决
关键直觉：**模板化攻击的副作用是文档之间高度相似**。攻击者用 GPT-4 批量生成"康德爱吃汉堡"类伪造文档时，文风、句式、长度都接近——这种"同质性"在 embedding 空间里形成可识别的聚类。同时，**伪造文档与真实知识库之间存在事实冲突**，LLM 的参数化知识能帮助识别。两个信号叠加，几乎所有"批量投毒"都会被抓。

**何时会失效**：
1. 攻击者**多样化生成**（同一目标用 10 种风格写）能逃过聚类阶段
2. 当攻击文档**事实正确但部分扭曲**（如"康德 1804 年去世"是真的但意图引导错误结论）时，LLM 自评估难以辨识
3. 大模型（如 GPT-4）做 self-assessment 成本不低

## 主要结果
- 在 NQ / TriviaQA / HotpotQA 等 4 个 RAG 数据集上：
  - 投毒 5 篇文档时，ASR 从基线的 90% 降到 **< 5%**
  - 投毒 20 篇时，ASR 从基线的 95% 降到 **< 15%**（其他方法此时基本失效）
- 推理成本：仅比 vanilla RAG 增加约 30%（不到 RobustRAG 的 N 倍）
- 在 GPT-4 / GPT-3.5 / Llama-3 上一致有效

## 局限性
1. 聚类参数（簇数 K）需要调优，对不同数据集略敏感
2. 自评估阶段对小模型效果有限（< 7B 的模型自评不准）
3. 对**单篇精心伪造**的高质量恶意文档防御较弱（无聚类信号）
4. 引入了额外推理调用，对成本敏感场景仍有负担

## 我们项目里的用法
**对应关卡**：第 3 关「RAG 防污染」的**主线方案**。
- **直接复用**：在我们的 RAG pipeline 里直接接入 TrustRAG 的两阶段过滤（GitHub 仓库代码可改造）
- **中文适配**：聚类阶段用中文 embedding 模型（如 BGE-M3 / Conan）；自评估用 DeepSeek-V2 中文能力强
- **数据合成**：用 PoisonedRAG 的方法生成 200 条中文政企场景投毒样本作为评测集
- **演示价值**：演示场景里"未防御 vs TrustRAG 防御"对比 ASR 数字差异大，视觉冲击强
- **结合**：与第 7 关 Traceback-RAG 联动——TrustRAG 拦截的事件落入审计日志、定位污染源

## 学习路径
- **必读**：1.2 方向防御侧最重要的 2025 论文，必读
- **5 分钟版**：看 Figure 1（双阶段架构）+ Table 2 主结果
- **30 分钟版**：Section 3「Method」+ Section 4 实验
- **跳过**：可以略过具体超参数实验
- **关键图**：Figure 1（pipeline）、Figure 4（聚类可视化）
- **配套阅读**：先看 PoisonedRAG 攻击，再看 TrustRAG 防御
- **动手**：本仓库代码质量高，建议跑通 demo
