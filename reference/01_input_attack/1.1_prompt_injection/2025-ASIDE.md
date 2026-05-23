# ASIDE: 在模型架构里物理分离指令和数据 (ASIDE: Architectural Separation of Instructions and Data in Language Models)

## 元信息
- **作者机构**: Egor Zverev 等 (IST Austria / ETH Zurich)
- **年份 · 发表**: 2025 · ICLR 2026
- **arXiv**: https://arxiv.org/abs/2503.10566
- **本地 PDF**: ./2025-ASIDE.pdf
- **代码**: https://github.com/egozverev/aside
- **难度**: 4/5

## 一句话总结
不靠 prompt、不靠分类器，**直接给模型的 embedding 层加一个"角色旋转"**——指令 token 和数据 token 用方向不同的 embedding 向量表示，模型从底层就知道谁是谁。

## 解决什么问题
之前所有防御（StruQ / SecAlign / Spotlighting / Llama Guard）都在做一件事："**用某种信号告诉模型谁是指令谁是数据**"——但这个信号要么写在 prompt 里（容易被模仿），要么编码在权重里（强对抗攻击下会被绕过）。

ASIDE 的观察：**真正彻底的分离应该在模型架构层面**。如果在 embedding 这一最底层就把"指令 token"和"数据 token"用方向正交的向量表示，那不论后面模型怎么算，这两类信息从一开始就不在同一个空间里——攻击者根本没办法把"数据"伪造成"指令"。

这是一种**结构性**而不是**学习式**的防御，理论上更鲁棒。

## 用了什么方法
**核心打比方**：之前的方案是给员工发不同颜色的工牌（蓝牌=主管，红牌=访客），但工牌可以伪造；ASIDE 是直接让员工和访客从两个不同的电梯进入大楼——根本不可能在同一个电梯里搞错身份。

**核心机制：条件性 embedding 旋转**
1. **加一个 role 标记**：输入 token 时附带它的角色（instruction 或 data）
2. **应用固定正交旋转**：对于"data"角色的 token，把它的 embedding 向量乘以一个固定的正交旋转矩阵 R（理论上等价于把它"投影到一个完全垂直的子空间"）
3. **不加新参数**：R 是固定的（如 90 度旋转），训练时只调原模型权重让它学会"在新的 embedding 空间里区分使用这两类信息"
4. **微调阶段**：用类似 StruQ 的对抗注入数据做 instruction tuning

**与之前方法的区别**：
- vs **ISE (Wu et al, 2024)**：ISE 用可学习的 offset 向量，ASIDE 用固定的正交旋转——后者更彻底、更深层有效
- vs **StruQ/SecAlign**：StruQ 用特殊 token 分隔，仍是表层信号；ASIDE 是 embedding 层分离
- vs **prompt-level 方法**：完全不靠 prompt，更难绕过

## 为什么能解决
关键直觉：正交旋转保证两个子空间的内积为 0——也就是说，在模型每一层的 attention/MLP 计算中，data 部分的信息要"投影回 instruction 子空间"才能被当作指令处理，但这个投影分量极小（接近 0）。**注入攻击在数学上变得指数级困难**：攻击者要把信息"从一个子空间挤到另一个子空间"。

**何时会失效**：
1. 极长的对抗输入可能通过模型深层的非线性产生跨子空间泄漏
2. 多模态场景（图片/音频）需要重新设计
3. 需要重新微调，不能即插即用

## 主要结果
- 在 Llama-3.1-8B / Qwen 2.5 7B / Mistral 7B v0.3 上验证
- 在 SEP（Separation Evaluation Protocol）指标上，instruction-data 分离度比 ISE 提升 **15-30%**
- 注入 ASR：相比基线降低 **40-60%**，无需额外安全训练
- 通用能力（MMLU 等）几乎无损
- 训练成本与普通 SFT 相当

## 局限性
1. 需要训练，闭源 API 不可用
2. 实现复杂度高于 StruQ（需要修改 embedding layer 前向逻辑）
3. 对**已知模型权重**的白盒强攻击（GCG）效果仍需测试
4. 与 LoRA / QLoRA 等参数高效微调的兼容性需要适配

## 我们项目里的用法
**对应关卡**：第 1 关「输入安检门」+ 第 4 关「三色信息流污点」的底层强化版。
- **借鉴思想**：ASIDE 的"角色感知 embedding"和我们方案里的"三色（公开/内部/机密）信息流污点"是同源思想——前者在模型内部分离，后者在系统外部分离。可以把 ASIDE 当作给基座模型加固的可选项
- **不一定要做**：实现成本较高，建议作为答辩"未来工作"提及，主线还是 StruQ + SecAlign + Spotlighting 三件套
- **学术价值**：在方案文档里引用 ASIDE，说明我们了解最新的结构性防御思路
- **如果做**：可以尝试在我们的 DeepSeek-V2 fine-tuning 阶段加一个简单版（仅在 token type ID 上区分指令/数据），作为 0.5 人月的探索亮点

## 学习路径
- **难度警告**：本文涉及向量空间几何，比 StruQ 难
- **5 分钟版**：看 Figure 1（rotated embedding 示意图）+ Table 1 主结果
- **60 分钟版**：Section 3「Method」+ Section 5 实验
- **跳过**：附录的数学证明可以选读
- **关键图**：Figure 1（架构图）、Figure 3（embedding 子空间可视化）
- **前置**：先读 StruQ 了解 baseline，再读 ASIDE 理解架构升级
