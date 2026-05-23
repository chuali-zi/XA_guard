# AgentSpec:智能体运行时可定制风险检测与缓解约束(AgentSpec: Customizable Runtime Enforcement for Timely Risk Detection and Mitigation in LLM Agents)

## 元信息
- **作者机构**: Haoyu Wang、Christopher M. Poskitt、Jun Sun 等 / 新加坡管理大学(SMU)
- **年份 · 发表**: 2026 · ICSE 2026(软件工程顶会)
- **arXiv**: https://arxiv.org/abs/2503.18666
- **本地 PDF**: ./2026-AgentSpec.pdf
- **代码**: https://github.com/SMU-IDS/AgentSpec(可能尚未公开,以论文中注明的为准)
- **难度**: 4 星 ★★★★

## 一句话总结
为智能体设计一套类 AOP(切面)的规则 DSL,让用户用接近自然语言的方式定义"什么时候该拦下来"。

## 解决什么问题
学界已有很多智能体防护方案(CaMeL、ShieldAgent、GuardAgent),但都有同一个问题:**规则硬编码、不可定制**。每家企业的合规要求不同——银行不许跨账户转账,医院不许批量导出病历,工厂不许在白班外修改 PLC——你不能让每家都改源码。AgentSpec 想解决的就是:**给客户一套 DSL,让他们能像写防火墙规则一样,用结构化但人话风格的语法定义安全约束;系统在运行时自动按规则拦截/审批/重写**。这是工程化落地的核心需求,我们项目要做的"中文政企 Policy DSL"完全是同一个方向。

## 用了什么方法
AgentSpec 的核心组件:

1. **规则 DSL 设计(类 AOP 风格)**:
   - 规则形式:`WHEN <trigger> CHECK <condition> THEN <action>`。
   - `trigger`:某个工具被调用之前/之后、某个值被产生、某种类别的输出等。
   - `condition`:布尔表达式,可访问当前任务上下文、用户身份、工具参数。
   - `action`:`block`(拦截)、`ask_user`(转人工)、`rewrite`(改参数后放行)、`log`(只记录不干预)。
   - 例:`WHEN tool=send_email CHECK recipient.domain != organization.domain THEN ask_user("即将外发邮件,确认?")`。

2. **运行时执行引擎**:
   - 智能体每次工具调用前,引擎查询所有规则,匹配的 rule 按优先级执行 action。
   - 引擎是 LLM-Agent-框架 agnostic 的——可插入 LangChain、AutoGen、自研 framework。
   - 支持规则**热更新**——管理员可在运行时增删规则,不重启服务。

3. **规则生成助手**:
   - 提供一个 LLM-based 工具:用户描述"我希望不要让模型把内部数据发到外部",LLM 自动生成对应的 DSL 规则草稿。
   - 草稿需要管理员审核+测试通过才能上线。

4. **覆盖测试与正确性**:
   - 为每条规则自动生成测试用例,跑全套场景验证规则不会误伤正常任务。
   - 提供"规则冲突检测器"——如果两条规则同时匹配但 action 矛盾(一个 block 一个允许),提示管理员消解。

类比:这就是"智能体的 iptables / WAF"——你写规则,系统执行。区别是规则能引用语义信息(不只是 IP/端口,还有"工具名""参数语义""用户角色")。

## 为什么能解决
关键设计:**让安全规则与业务逻辑解耦**。智能体开发者只管业务,合规部门写规则,两者在同一引擎中协同——这是 50 年来企业安全工程的成熟模式(SELinux policy、防火墙规则、IAM policy 都是这思路)。同时,DSL 比 Python 代码更接近自然语言,降低了合规人员的技术门槛。配合 LLM 辅助生成规则,真正做到了"非技术人员也能管安全"。

## 主要结果
- 在 AgentDojo、ToolEmu、Agent-SafetyBench 三个基准上跑 AgentSpec。
- 用 17 条人工规则覆盖 AgentDojo 攻击:ASR 从 32% 降到 5%。
- 用 LLM 辅助生成的规则:human review 通过率 73%,直接可用率 41%(剩下需要少量手改)。
- 性能开销:每次工具调用 +20-50ms(可接受)。
- 规则冲突检测:在 50 条规则规模下能在 < 5 秒发现冲突。

## 局限性
1. DSL 还相对底层,需要懂程序逻辑;真正的"自然语言写规则"仍是开放挑战。
2. LLM 辅助生成规则**可能漏掉边界情况**,需要人工补充测试。
3. 没有形式化验证支持(VeriGuard 是这方向的下一步)。
4. 规则间冲突在规模扩大后更复杂,需要更强的形式化工具。

## 我们项目里的用法
**对应关卡 3(规则编译) - 核心论文**。AgentSpec 是我们"中文 Policy DSL 编译器"最直接的对标:
- ① 直接学**它的 DSL 设计**(WHEN/CHECK/THEN 三段式),把英文换成中文,产出"中文 Policy DSL"v1.0 规范。
- ② 实现一个**对接 LangChain 的运行时引擎**,~600 行 Python 即可,把 trigger/condition/action 翻译成 LangChain Callback。
- ③ 写一个**雄安政企版规则库** v1.0:30 条人工规则覆盖"等保 2.0 GB/T 22239、GB/T 45654-2025 AI 安全要求"中的高频条款。这是我们的**核心创新**之一——把国家标准条文编译成机器可执行规则。
- ④ 用 DeepSeek-V2.5 做规则生成助手——管理员说"涉密邮件不能外发",LLM 自动产出 DSL 规则草稿。
- ⑤ 与 CaMeL 联动:DSL 规则可以约束 P-LLM 生成的工具调用计划(在 P-LLM 输出后、执行前那一层挂规则)。

## 学习路径
- **必读 Section 3 DSL 设计** —— 我们的 DSL 应基于其语法做中文化扩展。
- **看 Section 4 运行时引擎** —— 框架无关的设计哲学要继承。
- **看 Section 5 实验** —— 看用多少条规则能压住攻击,作为我们规则库规模的参考。
- **配合阅读 ShieldAgent 和 GuardAgent** —— 三者代表了 "DSL / 形式化逻辑 / 代码化" 三种规则表达形式,我们要取舍出一种。
