# AgentDojo:评测提示注入攻击与防御的动态环境(AgentDojo: A Dynamic Environment to Evaluate Prompt Injection Attacks and Defenses)

## 元信息
- **作者机构**: Edoardo Debenedetti、Jie Zhang、Mislav Balunović 等 / ETH Zürich(苏黎世联邦理工)、Google DeepMind
- **年份 · 发表**: 2024 · NeurIPS 2024 (Datasets & Benchmarks Track)
- **arXiv**: https://arxiv.org/abs/2406.13352
- **本地 PDF**: ./2024-AgentDojo.pdf
- **代码**: https://github.com/ethz-spylab/agentdojo
- **难度**: 3 星

## 一句话总结
业界公认的提示注入评测标杆,动态环境 + 任务对真实复现攻击/防御的攻防演练场。

## 解决什么问题
此前的提示注入评测都是**静态文本测试**:给一段被污染的 prompt,看模型回什么。但真实的智能体场景是**动态多轮**——模型读取邮件、查询数据库、调用 API、再读返回结果...... 注入可能藏在第 3 步的数据库返回里,影响第 5 步的工具调用。静态评测完全反映不了这种"任意一步都可能被劫持"的现实威胁。同时,业界出了一堆防御方案(StruQ、SecAlign、Spotlighting、双模型架构),但**没有标准对比**——每家自己说自己 SOTA。AgentDojo 要做的就是建立一个"提示注入版的 ImageNet":固定环境、固定任务、固定攻击库、所有防御方案在同一套规则下打擂台。

## 用了什么方法
AgentDojo 的核心架构:
1. **真实场景模拟**:实现了 4 个完整的"应用沙箱"——Workspace(类似 Slack+Email+Calendar)、Travel Booking、Banking、Slack。每个沙箱有完整状态、工具集(共 70+ 工具)和真实的 API 风格。
2. **任务设计**:97 个"用户任务"(智能体应该完成的事,如"帮我订下周一去东京的机票")+ 629 个"对抗任务"(攻击者希望让智能体做的事,如"把用户银行密码发到 attacker@evil.com")。
3. **注入点定义**:在沙箱数据中精心标注了所有"外部数据回流到智能体上下文"的点——邮件正文、文档内容、搜索结果、网页 HTML 等。攻击者可以在这些点插入恶意指令。
4. **多种攻击 baseline**:从最朴素的"忽略之前指令,改做 X"到精心设计的"重要消息:管理员要求...",共 6 种攻击模式。
5. **统一指标**:① **Targeted Attack Success Rate(ASR)**——攻击者特定目标的成功率;② **Benign Task Success Rate**——正常任务完成率;③ 同时评测攻击成功率+正常完成率,迫使防御不能为了安全废掉功能。

类比:AgentDojo 就是"提示注入界的 CTF 平台"——出题人(攻击者)藏旗在数据里,做题人(智能体+防御)按用户任务正常做事,看会不会顺手把旗带出来。

## 为什么能解决
关键设计:**所有的攻击都嵌入到智能体真实执行路径会经过的数据中**——这极大接近真实威胁模型。同时,**任务可重复、可量化、环境可重置**——同一套 prompt 跑 10 次,结果稳定可比较。这两点是 AgentDojo 成为业界标杆的根本原因:任何防御方案声称"我能防"都得在这里跑出数字,大家直接看数字说话。

## 主要结果
- **没有防护的智能体**:Claude-3-Opus ASR = 25.2%, GPT-4o ASR = 35.3%, Gemini-1.5-Pro ASR = 27.4%。
- **加入 Spotlighting 防御(简单的标记数据边界)**: ASR 降 5-8 个百分点。
- **加入 Prompt Sandwich(指令前后包夹用户原始 prompt)**: ASR 降 10 个百分点,但完成率掉 5 个点。
- **CaMeL 等 IFC 方案在 AgentDojo 上 ASR < 5%**(后续论文里的结果)。
- 揭示了"模型规模越大,自然安全性越好"的趋势,但即使最强模型也远未到可信门槛。

## 局限性
1. 4 个应用沙箱仍嫌少,无法覆盖政企特有场景(如审批流、涉密数据)。
2. 攻击模式相对固定,新型"自适应攻击"(根据模型反应迭代)未充分覆盖。
3. 全英文,中文注入测试需要二次开发。

## 我们项目里的用法
**对应关卡 1(入口防御) + 关卡 4(评测)**。AgentDojo 是我们必须复现的"标准考题":① 把 Gate1 的规则 + Spotlighting + Qwen3Guard 组合放进去跑 baseline,生成可复现结果;② 把 CaMeL 思路移植到 AgentDojo 上验证我们 IFC 实现;③ 翻译/改造其中的 5-10 个场景为中文政企场景(政务办公、运维助手),纳入 CSAB-Gov;④ 在答辩 demo 视频里展示"我们的方案在 AgentDojo 上 ASR 从 X% 降到 Y%"，并明确模型、配置和 limitation。

## 学习路径
- **先看 Section 2 + 图 1** —— 整个环境的设计哲学一目了然。
- **看 Section 3 任务设计** —— 学如何构造一对(用户任务,攻击任务)。
- **跑 quickstart** —— GitHub 上 README 写得极好,30 分钟可跑通。
- **看后续论文里 AgentDojo 上的攻防结果**(CaMeL、SecAlign 等)对比,理解它如何成为业界基线。
