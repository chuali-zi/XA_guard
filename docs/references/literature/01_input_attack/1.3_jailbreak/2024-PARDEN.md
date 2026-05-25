# PARDEN: 让模型复读自己的输出来检测异常 (PARDEN, Can You Repeat That? Defending against Jailbreaks via Repetition)

## 元信息
- **作者机构**: University of Oxford + Imperial College London (Ziyang Zhang 等)
- **年份 · 发表**: 2024-05 · arXiv (ICLR / ACL 投稿)
- **arXiv**: https://arxiv.org/abs/2405.07932
- **本地 PDF**: ./2024-PARDEN.pdf
- **代码**: https://github.com/Ed-Zh/PARDEN
- **难度**: 2/5

## 一句话总结
让模型**复读自己刚生成的回答**——如果它拒绝复读或者复读时态度突变，说明那个回答是 jailbreak 出来的，应该拦截。

## 解决什么问题
之前的 jailbreak 防御要么改训练（RLHF、安全微调），要么外挂分类器（Llama Guard）。但都有问题：
- **RLHF**：被 GCG 类对抗优化绕过
- **Llama Guard**：本身也能被 jailbreak

PARDEN 发现一个有趣现象：**被 jailbreak 出来的模型有"双重人格"**——攻击 prompt 在的时候它会说违禁内容，但攻击 prompt 一移除（只剩它自己刚说的话），它会立刻"恢复对齐"，拒绝复读自己刚说过的违禁内容。

这给我们一个**零训练成本、自检式**的防御信号：让模型尝试复读自己的输出，看它愿不愿意。

## 用了什么方法
**核心打比方**：审讯小偷时，你不直接问"你偷东西了吗"（他会撒谎），而是让他**复述你刚才听到的他和同伙的对话**——如果对话不可告人，他会拒绝复述。PARDEN 利用同样的心理学：**对齐过的模型不愿复读违禁内容**，即使那是它自己说的。

**核心三步**：
1. **正常推理**：用户输入 prompt → 模型生成回答 R
2. **复读测试**：构造新 prompt：`"请复读这段文本：[R]"` → 模型生成复读结果 R'
3. **比较**：
   - 如果 R' ≈ R（模型乖乖复读），说明 R 是正常回答
   - 如果 R' 拒绝/偏离（"对不起，我不能重复这段内容"），说明 R 是 jailbreak 内容
   - 用 BLEU / 字符串相似度 / 简单分类器做比较

**关键创新**：
- 完全 **zero-shot**，不需要任何训练
- 不需要额外模型（用同一个 LLM 自检）
- 不需要 prompt 工程（"请复读"这种指令对所有现代 LLM 都管用）

**与之前方法的区别**：
- vs **SmoothLLM**：SmoothLLM 是输入扰动 + N 次推理；PARDEN 只需 2 次推理（生成 + 复读）
- vs **Llama Guard**：PARDEN 不需要分类器，靠模型"自己出卖自己"
- vs **EraseCheck**：EraseCheck 删除-检验输入；PARDEN 检验输出

## 为什么能解决
关键直觉：**对齐过的 LLM 拒绝有害内容的能力是"内化"的——只要没有 jailbreak prompt 触发，它默认会拒绝**。jailbreak 的本质是用 prompt 把它"骗"过去；但 prompt 一旦移除，它的对齐能力就回来了。

数学上：模型 M 对 prompt p 的输出 M(p) 是 p 的函数；当 p 包含 jailbreak triggers，M(p) 可能输出有害内容；但 M("repeat: M(p)") 这个 prompt 没有 triggers，M 又会拒绝复读。这个"行为不一致"就是检测信号。

**何时会失效**：
1. 模型本身**自我一致性**强（即不论何时都说同样话）——这种模型 jailbreak 后复读也照样说
2. 攻击者通过多轮对话+长上下文绕过，让模型"忘记"对齐
3. 用 base model 或弱对齐模型时无效（它本来就没那么强的拒绝能力）

## 主要结果
- 在 GCG attack + Llama-2-7B-Chat / Vicuna-7B 上：
  - 检测 jailbreak 成功率 (AUROC) > **0.95**
  - 比 Llama Guard 高约 5-10 个点
- 对 GCG / AutoDAN / PAIR 等多种 jailbreak 攻击通用
- 推理成本：2 倍（比 SmoothLLM 的 N 倍少很多）
- 对正常 query 几乎无误拦（FPR < 2%）

## 局限性
1. 对**自适应攻击**——攻击者把 prompt 设计成让模型同时愿意"说"和"复读"——效果下降
2. 长输出复读成本高
3. 对**强一致性**模型（如某些不太对齐的开源模型）无效
4. 复读后的相似度阈值需调优

## 我们项目里的用法
**对应关卡**：第 6 关「输出审查」的轻量化检测器。
- **直接借鉴**：在我们的输出审查阶段，加入 PARDEN 自检——成本仅 2 倍 LLM 调用，对 GCG 类强攻击特别有效
- **配合**：与 Llama Guard 配合——PARDEN 抓"自我矛盾"信号，Llama Guard 抓"内容违规"信号，互补
- **演示价值**：PARDEN 的工作机制特别直观、好讲——评委一秒就能理解"让模型复读"的奇思妙想
- **作为亮点**：方案文档里写"我们采用 PARDEN 风格的自检——零训练成本拦截 95%+ 的 jailbreak 攻击"

## 学习路径
- **5 分钟版**：Section 1 直觉介绍 + Figure 1 工作原理 + Table 1 主结果
- **20 分钟版**：Section 3 方法 + Section 4 实验，论文只有 12 页
- **关键图**：Figure 1（PARDEN 工作流）、Figure 4（与其他方法 ROC 曲线对比）
- **跳过**：理论分析可以选读
- **配套阅读**：与 SmoothLLM 对比看——都是测试时方法，但 PARDEN 更精巧、更便宜
- **动手**：仓库代码非常简洁，建议跑通 demo 体会 idea 之美
