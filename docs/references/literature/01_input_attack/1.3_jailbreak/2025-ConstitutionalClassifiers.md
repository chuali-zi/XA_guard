# Constitutional Classifiers: Anthropic 用宪法分类器防御通用 jailbreak (Constitutional Classifiers: Defending against Universal Jailbreaks across Thousands of Hours of Red Teaming)

## 元信息
- **作者机构**: Anthropic (Mrinank Sharma 等)
- **年份 · 发表**: 2025-01 · arXiv (Anthropic 2025 安全报告)
- **arXiv**: https://arxiv.org/abs/2501.18837
- **本地 PDF**: ./2025-ConstitutionalClassifiers.pdf
- **代码**: 无开源（Anthropic 内部实现，但思路被广泛公开）
- **难度**: 3/5

## 一句话总结
Anthropic 把"宪法"（Constitutional AI 的安全规则）变成两个**轻量分类器**——一个查输入、一个查输出，部署到 Claude 上扛过了 3000+ 小时红队测试。

## 解决什么问题
Anthropic 一直在做 Claude 的安全工作，他们的 Constitutional AI（宪法式 AI）思路是：用一组"宪法原则"（如"不输出 CBRN 武器配方"）来训练模型自我审查。但这种"内化在权重里"的安全有两个问题：
1. **对未来攻击的适应性差**：宪法是训练时定的，新出的 jailbreak 招式它没见过
2. **训练成本高**：每改一条宪法要全量重训

Anthropic 想要一个**"宪法分类器"层**——把同样的宪法规则做成轻量分类器外挂在主模型外面，能快速更新（无需重训主模型）、能针对未见过的攻击 zero-shot 泛化、能在大规模红队测试下站住脚。

## 用了什么方法
**核心打比方**：
- 之前的 Constitutional AI：把宪法**刻在员工脑子里**（费时费力，更新难）
- Constitutional Classifiers：在公司大门**挂一份宪法 + 两个保安**——一个查进来的人（输入分类器），一个查送出去的文件（输出分类器）

**关键设计**：
1. **基础数据合成**：用 LLM 根据宪法规则**自动生成训练样本** —— 正样本（违反宪法的 prompt/response）+ 负样本（普通对话）
2. **两个分类器**：
   - **Input Classifier**：判断用户 prompt 是否在请求宪法禁止的内容（如"请教我制毒"）
   - **Output Classifier**：判断模型回答是否包含宪法禁止的内容（如详细的化学合成步骤）
3. **轻量架构**：用小型分类器（比主模型小一个数量级），推理快、易部署
4. **持续更新**：发现新的 jailbreak 后，针对性扩充训练数据 + 短时重训（小时级别）

**红队大规模验证**：Anthropic 邀请了大量红队员（外部研究者、专业红队公司）做**3000+ 小时**的对抗测试，覆盖 12 种 CBRN（化学/生物/放射/核）等高敏感主题。这是**业界规模最大的 jailbreak 红队**之一。

**与之前方法的区别**：
- vs **Constitutional AI 原版**：那是训练阶段；本文是部署阶段的外挂分类器
- vs **Llama Guard**：Llama Guard 用通用类别（暴力/仇恨/性内容等）；Constitutional Classifiers 是**宪法驱动**的，更针对 Anthropic 自家定义的高风险类别
- vs **SmoothLLM/PARDEN 测试时方法**：CC 是分类器外挂，推理成本低很多

## 为什么能解决
关键直觉：**Jailbreak 攻击的成功依赖于"主模型被骗"**；外挂分类器**不通过主模型**就能直接判断输入/输出是否违规——攻击 prompt 影响不到它的判断（除非攻击者同时对分类器做对抗，但这需要白盒）。

而宪法分类器的"轻量+持续更新"特性让它能跟上攻击的演进。

**何时会失效**：
1. 攻击者**针对分类器**做对抗（如用对抗输入欺骗分类器把恶意内容判为安全）—— 这是 *Attacker Moves Second* 论文专门警示的
2. 分类器训练数据未覆盖的新攻击类型 zero-shot 性能不够
3. 极隐蔽的多轮攻击（多轮慢慢引导）可能逃过单轮判断

## 主要结果
- 经过 3000+ 小时红队测试，宪法分类器把 jailbreak 成功率从 **86%** 降到 **4.4%**
- 对未见过的 jailbreak 攻击 zero-shot 召回 > 90%
- 推理延迟仅 +**0.5%**（轻量分类器）
- 对正常 query 的拒绝率（"安全税"）：+0.38%（极低误拦）
- 已部署在 Claude API 生产环境

## 局限性
1. 主要面向**高风险话题**（CBRN 等），对一般 jailbreak（如让模型说脏话）覆盖不全
2. **未开源**：Anthropic 公开了方法但没开源代码/模型
3. **Attacker Moves Second** 论文显示：当攻击者了解分类器后，仍能找到对抗输入；CC 也不能完全免疫
4. 对**指令分歧**（让模型做边缘合法但用户不想做的事）这类灰色场景判定困难

## 我们项目里的用法
**对应关卡**：第 1 关「输入安检门」+ 第 6 关「输出审查」的**架构指导**。
- **架构借鉴**：我们的"宪法"= 中文政企合规规则（等保 2.0 / TC260-003 / GB/T 45654）。可以用 Constitutional Classifiers 的方法论：
  1. 用 LLM 根据合规规则**自动合成训练数据**（200-500 条）
  2. 训练两个轻量分类器（基于 Llama Guard 1B 或 BERT）做输入/输出审查
  3. 持续根据新发现的攻击模式扩充训练集
- **关键经验**：**红队测试是必需的**——我们的方案要规划专门的红队环节，哪怕规模小（如 10-20 小时）
- **演示价值**：在方案中明确引用 Anthropic 的 3000 小时红队 + 4.4% ASR 的数据，作为"我们方法论的工业标准背书"
- **现实主义**：**Attacker Moves Second** 的警示要记住——单纯的输入输出分类器不能解决一切，要配合 IFC（信息流控制）+ sandbox 做纵深

## 学习路径
- **必读**：方向 1.3 重要论文之一，Anthropic 的工业实践经验
- **5 分钟版**：Figure 1 架构图 + Section 1 + Table 1 主结果
- **45 分钟版**：Section 3-5（方法 + 评估 + 红队结果）
- **关键图**：Figure 1（双分类器架构）、Figure 5（不同攻击类别的检测召回率）
- **跳过**：Anthropic 内部部署细节可以选读
- **配套阅读**：与 Llama Guard 对比看（两家大厂思路异同）+ Attacker Moves Second（看局限性）
