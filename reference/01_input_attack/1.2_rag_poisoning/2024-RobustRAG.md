# RobustRAG: 用"隔离-聚合"实现可证明鲁棒的 RAG (Certifiably Robust RAG against Retrieval Corruption)

## 元信息
- **作者机构**: NVIDIA + Princeton + UC Berkeley (Chong Xiang, Danqi Chen, Prateek Mittal 等)
- **年份 · 发表**: 2024 · arXiv (Princeton + 顶会团队)
- **arXiv**: https://arxiv.org/abs/2405.15556
- **本地 PDF**: ./2024-RobustRAG.pdf
- **代码**: https://github.com/inspire-group/RobustRAG
- **难度**: 4/5

## 一句话总结
把检索到的 K 篇文档**分成不重叠的组**，每组独立让 LLM 生成答案，再用安全聚合算法把多个答案合并——少数恶意文档无法主导最终输出，理论上可证明鲁棒。

## 解决什么问题
PoisonedRAG 已经证明 RAG 投毒攻击门槛低、危害大。**TrustRAG 用聚类过滤是经验式防御**，遇到攻击者自适应应对仍可能崩溃。RobustRAG 想达到一个更高的目标——**可证明鲁棒性（certifiable robustness）**：在数学上证明"只要恶意文档数量不超过 N，最终答案的质量有下界保证"。

这种"证明"很重要，因为：
1. 安全防御往往是猫鼠游戏，但**可证明**的方法对未来攻击也有保证
2. 在政企场景（金融、医疗、政务）需要给监管/审计提供可量化的安全承诺
3. 学术上是一个跳跃——从启发式防御变成形式化方法

## 用了什么方法
**核心打比方**：法官审案不能只听一个证人；要听 K 个独立证人，且证人之间不能串供。如果 K 个里有 1-2 个被收买（恶意文档），多数证词仍然真实——法官按"多数票"判决，结果就不容易被少数收买者操纵。

**Isolate-then-Aggregate 三步流程**：
1. **检索**：常规 RAG 检索 K 篇文档（如 K=10）
2. **隔离 (Isolate)**：把 K 篇分到 N 个不相交组里（如 N=5，每组 2 篇）。每组**独立**喂给 LLM 生成中间答案，组之间不共享上下文——确保少数恶意文档只能影响少数中间答案
3. **安全聚合 (Secure Aggregate)**：把 N 个中间答案合并成最终答案。RobustRAG 提供两种聚合算法：
   - **Keyword Aggregation**：每个答案提取关键词集合，按"出现频次"投票选出最终关键词，再用关键词重新生成答案
   - **Decoding Aggregation**：在 token 解码层面，每个 group 独立给出下一个 token 的概率分布，取**安全聚合**（如截断 top-k 后求和）作为最终 token 分布

**为什么可证明**：因为聚合算法的输出对少数 group 的扰动**不敏感**——攻击者要扰动最终输出，必须污染足够多个 group。如果污染数 < 阈值，最终输出与"无污染"情况相同。

**与之前方法的区别**：
- vs PoisonedRAG / 经验防御：RobustRAG 提供**形式化保证**
- vs TrustRAG：TrustRAG 用聚类启发式去除可疑文档（可能误删，无下界）；RobustRAG 用隔离-聚合（保留所有，靠投票稀释）
- vs ensemble：传统 ensemble 多模型投票；RobustRAG 是**同一模型多次独立调用**+ 投票

## 为什么能解决
关键直觉：**信息聚合的鲁棒性来自冗余 + 独立**。K 篇文档独立分组后，污染 N 个 group 中的 t 个最多影响 t 个答案。聚合算法保证"t 个答案的扰动 < 阈值时最终输出不变"——这就是 majority vote 的鲁棒性原理，但搬到了文本聚合上。

**何时会失效**：
1. 攻击者注入的恶意文档数量超过保证阈值（如 5 个 group 里污染了 3 个）
2. 聚合算法需要 N 次 LLM 调用，**成本线性增长**
3. 对**长篇输出**（多句话答案）聚合效果较差，关键词聚合损失语义流畅度

## 主要结果
- 在 NaturalQuestions / RealtimeQA 等 RAG 数据集上：
  - 注入 1 篇恶意文档时，可**形式化证明**回答正确性下界 > 70%
  - 注入 3 篇时仍能保证下界 > 40%
- 与 vanilla RAG 相比，无攻击时性能略降（约 -5%），有攻击时显著优于 vanilla
- 推理成本：N 倍 LLM 调用（典型 N=5，即 5 倍开销）
- 兼容 GPT-4 / Llama-3 / Mistral 等多种 LLM

## 局限性
1. **N 倍推理成本**，对成本敏感场景不友好
2. 关键词聚合丢失流畅度，decoding 聚合实现复杂
3. 可证明阈值依赖污染文档数量假设，实际部署难以保证
4. 长文档/对话场景的扩展性需进一步研究

## 我们项目里的用法
**对应关卡**：第 3 关「RAG 防污染」的核心算法选项之一。
- **是否采用**：与 TrustRAG 二选一或组合。我们方案推荐**先用 TrustRAG (cluster + self-assess) 作为主线（成本低、SOTA），把 RobustRAG 作为"高安全场景"的可选模式**
- **学术亮点**：在方案文档里提到"我们支持可证明鲁棒模式"，给评委专业感
- **演示场景**：可以做一个"金融/医疗等高敏感场景"的演示分支，启用 RobustRAG，展示对 PoisonedRAG 攻击的形式化保证
- **可重用代码**：RobustRAG GitHub 仓库代码质量高，可以直接 fork 并改造为中文场景

## 学习路径
- **难度警告**：本文有较多数学符号，初学者建议先读 PoisonedRAG 和 TrustRAG 再回头看
- **5 分钟版**：Figure 1（架构图）+ Figure 2（聚合算法示意）+ Table 1 主结果
- **60 分钟版**：Section 3「Method」+ Section 4「Robustness Analysis」+ Section 5 实验
- **跳过**：可以略过部分形式化证明（理解直觉即可）
- **关键图**：Figure 1（Isolate-then-Aggregate）、Figure 3（关键词聚合 vs 解码聚合）
- **配套阅读**：先看 PoisonedRAG（攻击）→ TrustRAG（启发式防御）→ 本文（可证明防御）
