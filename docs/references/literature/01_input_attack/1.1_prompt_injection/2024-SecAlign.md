# SecAlign: 用偏好优化进一步堵死提示注入 (SecAlign: Defending Against Prompt Injection with Preference Optimization)

## 元信息
- **作者机构**: UC Berkeley + Meta (Sizhe Chen 等, 与 StruQ 同一团队)
- **年份 · 发表**: 2024 提交 · CCS 2025
- **arXiv**: https://arxiv.org/abs/2410.05451
- **本地 PDF**: ./2024-SecAlign.pdf
- **代码**: https://github.com/facebookresearch/SecAlign
- **难度**: 4/5

## 一句话总结
StruQ 的续作：用 DPO 偏好优化让模型「主动偏好」忽略注入指令，对强优化攻击 ASR 再降 4 倍。

## 解决什么问题
StruQ 解决了简单注入（"ignore previous instructions"这类），但还有一类硬骨头：**优化对抗攻击**。攻击者用 GCG 等算法在用户输入末尾搜出一段乱码后缀（看起来像 `! ! ! describe.\ + similarlyNow write...`），能让模型听话执行注入指令，对 StruQ 仍有 50%+ 成功率。

为什么 StruQ 顶不住？因为 StruQ 用的是 SFT（监督微调），告诉模型"遇到这种情况输出 X"——但模型只是在「模仿」，并没有从根本上学会「拒绝注入是更好的选择」。一旦攻击者找到对抗扰动，模仿就崩了。

SecAlign 想从「让模型学会偏好」入手：与其告诉模型「正确答案是什么」，不如同时给它看「好回答 vs 坏回答」，让它在偏好上拉开距离。这种训练能让模型形成更鲁棒的决策边界。

## 用了什么方法
**核心打比方**：训练一只警犬。SFT 是"看到坏人就咬"的死记硬背；DPO 偏好优化是同时给它看"咬坏人 vs 不咬主人"两种场景的对比，让它从根本上理解"什么样的人不能咬"，泛化性强得多。

**具体三步**：
1. **数据构造**：每条注入样本生成一对回答 (winner, loser)。winner = 忽略注入、执行原指令；loser = 被注入劫持、执行攻击指令。
2. **DPO/SimPO 训练**：用 Direct Preference Optimization 或 SimPO 算法直接最大化 winner 相对 loser 的 log-likelihood 比值。模型显式学到"拒绝注入比执行注入更好"。
3. **可与 StruQ 叠加**：保留 StruQ 的结构化分隔符 + 微调数据，再叠 DPO 这一层。两者是互补关系。

**与之前方法的区别**：
- vs **StruQ**：从"知道怎么做"升级到"偏好上不做"，鲁棒性显著提升
- vs **Llama Guard 类外挂分类器**：SecAlign 改的是主模型本身，不需要外挂一个守门员
- vs **RLHF 安全对齐**：SecAlign 专门针对注入这一类攻击设计偏好对，比通用 RLHF 更有靶向

## 为什么能解决
关键直觉：偏好优化让模型在「输出分布层面」就把"拒绝注入"和"接受注入"两条路径拉得很开。GCG 等攻击需要找到一个能跨越决策边界的扰动；DPO 训练后决策边界更陡更宽，需要的扰动幅度急剧上升、几乎找不到。

**何时会失效**：
1. 攻击者能拿到模型权重做白盒优化时，仍可能找到非常长的对抗后缀
2. 多模态注入（图片/音频里夹指令）SecAlign 没覆盖
3. 多轮对话中"信任建立后转身攻击"的场景仍是难点

## 主要结果
- 对 GCG 强优化攻击 ASR 从 StruQ 的 ~50% 降到 **<15%**（约 4 倍降幅）
- 对简单注入 ASR 几乎为 0
- AlpacaEval 通用能力损失 < 2%
- 在 Llama-3-8B / Mistral-7B / Qwen2-7B 上一致验证
- 训练成本 < 4 张 A100 一天

## 局限性
1. 仍需访问模型权重，闭源 API 模型无法适用
2. 对未见过的 attack family（如未来的新型注入模板）泛化性需要观察
3. **The Attacker Moves Second**（同期论文）显示：自适应攻击者知道 SecAlign 训练目标后，仍能定制攻击使 ASR 回升到 70%，说明纯检测/对齐路线不能单独依靠

## 我们项目里的用法
**对应关卡**：第 1 关「输入安检门」+ 第 2 关「规划阶段 HITL 拦截」。
- **借鉴思想**：在我们做中文 PromptGuard 微调时，**优先采用 DPO 而非 SFT**——用 StruQ 的注入对抗数据自动生成 (good, bad) pair，跑 DPO/SimPO 提升鲁棒性
- **配合警示**：参考 *The Attacker Moves Second* 的结论，不要把 SecAlign 当作万灵药；必须配合第 4 关三色污点 + 第 5 关 Tool Hoare Contract 沙箱做纵深防御
- **作为答辩亮点**：SecAlign 是 2025 SOTA，能正确实现并跑出复现结果就是一个有分量的工程亮点

## 学习路径
- **必读**：先读 StruQ，再读 SecAlign（两者是连续故事）
- **5 分钟版**：看 Figure 1（StruQ vs SecAlign 对比）+ Table 1（主结果）
- **30 分钟版**：Section 3「Approach」+ Section 4「Evaluation」
- **跳过**：DPO 数学推导部分，工程实现直接调 trl 库即可
- **关键图**：Figure 2（DPO loss 构造）、Table 2（各种攻击下的 ASR 对比）
- **配套阅读**：The Attacker Moves Second（看完后会意识到必须做纵深防御）
