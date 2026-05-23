# 无需提示的思维链推理 (Chain-of-Thought Reasoning Without Prompting)

## 元信息
- **作者机构**: Google DeepMind (Xuezhi Wang, Denny Zhou)
- **年份 · 发表**: 2024 · NeurIPS 2024
- **arXiv**: https://arxiv.org/abs/2402.10200
- **本地 PDF**: ./2024-CoT-No-Prompt.pdf
- **代码或项目主页**: (官方未公开发布)
- **难度**: 3 颗星

## 一句话总结
不用"Let's think step by step", 模型自己就能 CoT —— 关键在采样阶段而非 prompt。

## 这篇论文研究什么
2022 年 CoT 出现以来, 大家都默认"必须用 prompt 触发 CoT", 比如加一句 "Let's think step by step"。但这篇论文问了个非常深的问题: 模型默认就有 CoT 能力吗?如果有, 为什么必须靠 prompt 才能激发?

之前的研究:
- 默认认为 "CoT 是 prompt engineering 的产物"
- 评估推理能力时, 永远先加 CoT prompt 再看效果
- 没人问过"不加 prompt 时, 模型 top-K 候选答案里有没有藏着 CoT"

## 它提出了什么方法
作者改了一个小到几乎没人会想到的东西: 解码策略。

**核心发现**:
- 普通生成: 用 greedy 或 top-1 采样, 总是输出"直接答案"(可能错)
- 但: 看 top-K 候选(K=5 或 10), 第 K 个候选答案常常**自带 CoT 推理过程**!
- 也就是说, 模型其实内部"想了一下", 只是 greedy 让它选了短答案

**方法: CoT-Decoding**
1. 推理时不用 greedy
2. 看每一步的 top-K candidates
3. 选"包含推理痕迹"的那条路径(用置信度差作为信号)
4. 不需要任何 prompt 改动

**关键证据**:
- 在 GSM8K 数学题: 默认 token 准确率 16.5%, CoT-Decoding 提升到 50%+
- 没改 prompt, 没改模型, 只改采样

打个比方: 之前以为模型是"懒学生, 你不让它写过程它就不写", 这篇论文发现其实模型脑子里"已经写了草稿纸", 只是输出时没把草稿纸递上来; 改一下"递作业的方式"(top-K 选择), 草稿纸就出现了。

## 为什么这个方法有效
关键洞察: LLM 的能力不仅在 logits 顶部, 也在 top-K 中。Greedy decoding 是有损的。失效场景: 需要 K 足够大才能找到 CoT 路径; 对模型置信度差不大的任务效果有限。

## 主要实验结果
- GSM8K(数学): 16.5% → 51.5%
- MultiArith: 32% → 79%
- 在 PaLM-2 和 Mistral 上都验证有效
- 不依赖 prompt, 与 CoT prompt 可叠加 (combined 效果更好)

## 局限性
1. 需要看 top-K candidates, 部分闭源 API 不支持
2. 计算开销略增(虽不大)
3. 不是所有任务都受益, 简单任务可能没帮助

## 我们项目里的用法
**与可信度审计的关联**: 这篇论文表面在讲"提升推理性能", 实际对审计有深远意义 —— **CoT 不是 prompt 的产物, 是模型固有能力**。意味着:
1. 我们项目要审计 CoT 时, 不能依赖"模型只在被 prompt 时才显式 CoT"
2. 模型可能在"内部"做了 CoT 但没暴露, 黑匣子需要更深层(top-K logits)的记录
3. 与 Faithful-CoT 那篇结合看: CoT 文字 ≠ 真实推理, 真实推理在 top-K 分布里

对关卡 6 的具体启发: 黑匣子记录不应只记"输出文本", 还应记录每步的 top-K logits 和置信度差。这是可解释审计的关键信息源。

## 学习路径
1. 读论文 §2-3 即可掌握核心方法
2. 跑一遍 GSM8K 实验, 体会 top-K 解码的效果
3. 把"top-K logits 记录"加入关卡 6 黑匣子日志规范
