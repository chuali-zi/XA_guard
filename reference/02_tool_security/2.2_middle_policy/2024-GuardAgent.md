# GuardAgent:用一个"看守智能体"保护其他智能体(GuardAgent: Safeguard LLM Agents by a Guard Agent via Knowledge-Enabled Reasoning)

## 元信息
- **作者机构**: Zhen Xiang、Linzhi Zheng、Yanjie Li、Junyuan Hong、Qinbin Li、Han Xie、Bo Li 等 / UIUC、UC Berkeley、芝加哥大学
- **年份 · 发表**: 2024 · arXiv 预印 / NeurIPS 2024 Workshop / 后续 SP 2025 投稿
- **arXiv**: https://arxiv.org/abs/2406.09187
- **本地 PDF**: ./2024-GuardAgent.pdf
- **代码**: https://github.com/guardagent/guardagent
- **难度**: 3 星

## 一句话总结
不在被保护 agent 内嵌检测,而是用一个独立的 Guard Agent 在外面监视,并把规则编译成可执行的 Python 代码。

## 解决什么问题
之前的防御都是"在 LLM 内部加约束"——改 prompt、加分类器、改 decoding。问题是:① 你必须修改/控制被保护的 LLM;② 单 LLM 内部的判断容易被 prompt 注入欺骗(同一份输入既用于"做事"又用于"判断该不该做")。GuardAgent 提出**外部看守模式**:一个独立的"看守者"智能体读取被保护者的完整上下文,根据预定义规则判断每一步是否合规。这与企业里的"四眼原则"(two-man rule)一致——重大操作必须有第二个人审核。

## 用了什么方法
GuardAgent 的核心流程:

1. **规则收集**:管理员用自然语言写一组安全规则(如"不可发送医疗数据到外部域"),GuardAgent 把每条规则转为机器可理解的元数据 + 嵌入向量。

2. **Guard Agent 自身的"推理-编码"循环**:
   - 在每次目标 agent 准备执行工具调用时, Guard Agent 收到:① 用户指令;② 当前任务上下文;③ 即将执行的 action(工具名+参数)。
   - Guard Agent 用 LLM **生成一段 Python 代码**——这段代码读取当前状态,检查所有相关规则,输出 verdict。
   - 代码在沙箱执行,verdict 决定:`allow / block / ask_user`。
   - 这种"LLM 生成可执行代码"模式比"LLM 直接判断"更稳健——代码可审计、可单测、不会被 prompt 注入翻盘。

3. **知识图谱辅助**:
   - 规则库 + 历史决策都进入一个知识图谱,Guard Agent 检索相关上下文做更准确判断。
   - 例:"上次类似情况下用户授权过 X,本次同条件下可继承"——避免反复打扰用户。

4. **延迟优化**:
   - Guard Agent 的代码生成是关键瓶颈——作者用 fine-tune 的小模型(7B)替代 GPT-4 做这一层,延迟可控在 200ms 内。

类比:GuardAgent 像"工厂里的安全员"——他不参与生产,只在边上看每个动作,见到危险就喊停,且每次报警都留下书面记录。

## 为什么能解决
两个关键设计:① **隔离的看守者**——Guard Agent 用独立模型/会话,不会被目标 agent 的污染状态影响;② **代码化规则执行**——把"判断"从模糊的 LLM 自然语言推理变成确定的代码执行。这两个设计来自传统软件安全(reference monitor 模式、capability-based security),已被证明有效。

## 主要结果
- 在 EHRAgent(医疗智能体)和 Mind2Web(网页智能体)上跑评测。
- EHRAgent 上违规率从 baseline 14% 降到 1.5%(Guard Agent 介入)。
- Mind2Web 上类似改善。
- LLM 生成的判断代码**准确率 89%**,人工复查不需要修改的 76%。
- 平均延迟 +180ms,可接受。

## 局限性
1. Guard Agent 自身也是 LLM,可能被精心设计的 adaptive 攻击影响。
2. 规则数增多时,知识图谱检索复杂度上升。
3. **生成代码的安全性**——如果 Guard Agent 错误生成了一段误判规则的代码,可能漏过攻击或误伤正常操作;需要规则代码经过 review/测试。
4. 不解决工具内部的执行后影响(那是 sandbox 层的事)。

## 我们项目里的用法
**对应关卡 3(规则编译)的另一种实现方式**。我们可以把 GuardAgent 当作 AgentSpec 的**轻量替代/补强**:
- ① 对于结构化规则,用 AgentSpec 风格的 DSL(精确、快)。
- ② 对于复杂语义判断("这个内容是否涉密"这种需要理解上下文的),用 GuardAgent 风格的 LLM-生成-代码模式。
- ③ **二者组合**:DSL 规则 + LLM 生成判断代码,在 Policy DSL 编译器里同时支持两种规则源。
- ④ 借鉴**知识图谱**:把历史 HITL 决策(用户批准过的)沉淀为规则,避免重复打扰。

## 学习路径
- **看 Section 3 架构图** —— 一图秒懂"外部看守"模式。
- **看 Section 4 代码生成流程** —— LLM 生成 Python 判断代码的 prompt 模板,可直接复用。
- **看 Section 5 EHRAgent 案例** —— 医疗场景的规则化设计,对我们做政企"敏感数据保护"有直接借鉴。
- **配合阅读 ShieldAgent** —— ShieldAgent 用 MLN(声明式),GuardAgent 用 Python 代码(命令式),二者代表两种实现哲学。
