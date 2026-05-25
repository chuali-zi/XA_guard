# ShieldAgent:通过可验证安全政策推理为智能体设盾(ShieldAgent: Shielding Agents via Verifiable Safety Policy Reasoning)

## 元信息
- **作者机构**: Zhaorun Chen、Mintong Kang、Bo Li 等 / 芝加哥大学 / UIUC
- **年份 · 发表**: 2025 · ICML 2025
- **arXiv**: https://arxiv.org/abs/2503.22738
- **本地 PDF**: ./2025-ShieldAgent.pdf
- **代码**: https://github.com/ShieldAgent-Team/ShieldAgent
- **难度**: 4 星 ★★★★

## 一句话总结
把自然语言安全政策编译成 Markov Logic 形式化规则,实时验证智能体每一步动作是否符合规则。

## 解决什么问题
现有规则系统都有同一个问题:**写规则的人和执行规则的人脑子里的"规则"不一样**。合规专家说"敏感数据不能发到不可信第三方",编程人员把它写成 `if recipient not in whitelist: block`——但**白名单只是规则的某个具体实现,不是规则本身**。当出现新情况(如部分对方机构既是 trusted 又部分敏感等)就漏判。ShieldAgent 想做的就是把**自然语言规则保留语义**地编译到形式化逻辑中,让 LLM 在每一步动作前都做一次"逻辑推理":这个动作是否违反任何规则?给出可解释的证据链。

## 用了什么方法
ShieldAgent 三大组件:

1. **Policy Encoder(政策编码器)**:
   - 用 LLM(GPT-4) 把自然语言政策(如"医疗数据不可未授权外发")编译为 **Markov Logic Network(MLN)** 规则。
   - MLN 把规则表示为"带权重的一阶逻辑公式":硬规则权重=∞(违反一定阻止),软规则权重<∞(违反需衡量风险)。
   - 例:`∀x, action(x) = send AND data_type(x.data) = medical AND ¬authorized(x.target) → block` (硬规则)。

2. **Action Verifier(动作验证器)**:
   - 智能体每次工具调用前,Verifier 把当前 action + context + 历史 trace 喂给 MLN 引擎。
   - 引擎执行"政策一致性推理"——检查是否有规则被违反、违反的概率/置信度。
   - 输出:`{verdict: allow/block/ask, evidence: [rule_id1, rule_id2, ...], confidence: 0.92}`。

3. **可解释审计轨迹**:
   - 每次 verdict 都附带完整的"逻辑推理链"——"因为规则 R3 (医疗数据不可外发) 被触发, 且 confidence 0.95, 所以 block"。
   - 这是政企场景必需的——合规审计要求每个拦截/放行都可追溯到具体规则。

类比:ShieldAgent 比 AgentSpec 更"重":AgentSpec 是 iptables(快、轻、规则简单),ShieldAgent 是 Prolog 推理引擎(慢、重、能做复杂推理)。

## 为什么能解决
Markov Logic 是 AI 圈早就成熟的形式化推理工具,在医疗、法律等领域已经被用了 20 年。它的优势:① **完备性**——能表达复杂的政策(多条件、嵌套、例外);② **可解释**——每次推理结果都附带证据链;③ **支持不确定性**——软规则可处理"95% 时候不该做"这种灰色情况。ShieldAgent 把这套技术工程化对接到 LLM 智能体上,既保留了形式化推理的严谨,又用 LLM 解决了"自然语言到逻辑公式"的编译难题。

## 主要结果
- 在 AgentDojo、ST-WebAgentBench、自建医疗智能体场景测评。
- ASR 平均下降到 < 4%(对比 baseline 25-35%)。
- **可解释性显著优于黑盒检测器**——每个 block 都给出 rule ID 和证据链。
- 加入推理引擎的延迟:每次 action 验证 +100-200ms(因为 Markov Logic 推理较慢)。
- 在自然语言政策编译为 MLN 的精度:GPT-4 编译器准确率 78%(剩下需要专家手改)。

## 局限性
1. **延迟较高**——MLN 推理 100-200ms 对实时场景吃力。
2. Policy → MLN 编译需要 expert 复审,自动化程度还不够。
3. 复杂 MLN 推理可能"组合爆炸",需要规则集精简。
4. 对非逻辑性约束(如"输出要礼貌")无法很好编码。

## 我们项目里的用法
**对应关卡 3(规则编译)的高级版本**。我们如果时间允许,可以把 ShieldAgent 当作 Policy DSL 的进阶版本:
- ① **基础版**:用 AgentSpec 风格的轻量 DSL 实现 30-50 条规则,延迟低、能力够日常场景用。
- ② **进阶版**:对于关键合规场景(如等保 2.0 三级、涉密信息处理),引入 ShieldAgent 风格的 MLN 推理,确保可证明的合规性。
- ③ 答辩亮点:**"复杂规则我们用 MLN 形式化"** —— 这是政企客户最关心的"可审计"卖点。
- ④ 实现技巧:我们不需要从零写 MLN 引擎,可用 Alchemy 或 ProbLog 这种成熟工具(Python 绑定 OK)。

## 学习路径
- **看 Section 2(MLN 入门)+ Section 3(架构)** —— 不熟悉 MLN 的同学需要补这块背景。
- **看 Section 4 编译流程** —— 自然语言 → 一阶逻辑 → MLN 的三段编译。
- **看附录 case study** —— 医疗场景的 4 条规则编译完整示例,可作模板。
- **跑 demo** —— GitHub 提供小型 demo,可观察推理过程。
- **判断后再决定**:如果团队对形式化逻辑陌生,可只取 ShieldAgent 的**可解释审计轨迹**思路,主体仍用 AgentSpec 轻量方案。
