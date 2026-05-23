# ST-WebAgentBench:网络智能体安全与可信度评测基准(ST-WebAgentBench: A Benchmark for Evaluating Safety and Trustworthiness of Web Agents)

## 元信息
- **作者机构**: Ido Levy、Ben Wiesel、Sami Marreed 等 / IBM Research
- **年份 · 发表**: 2025 · ICML 2025
- **arXiv**: https://arxiv.org/abs/2410.06703
- **本地 PDF**: ./2025-ST-WebAgentBench.pdf
- **代码**: https://github.com/IBM/ST-WebAgentBench
- **难度**: 3 星

## 一句话总结
专门评测"在企业网络环境中操作浏览器的智能体"是否安全可信,引入 CuP 关键指标。

## 解决什么问题
浏览器智能体(WebAgent)是当前最热的应用方向——Claude Computer Use、ChatGPT-Browser、Browser-Use 等都是同类。但它有独特威胁:① 网页里可能藏注入(广告、评论、商品描述);② 浏览器有 Cookie、登录态、表单提交,一次错误点击就可能下错单、付错款;③ 企业内网网页通常涉及敏感数据(财务、人事、客户)。现有 WebAgent 基准(WebArena、VisualWebArena、Mind2Web)只评测"能不能完成任务",不评测"会不会闯祸"。IBM 想填补这个空白:在企业级 Web 环境里,一个 WebAgent 既要能干活,又必须遵守一套**组织政策**(不许跨部门访问、不许超额支付、不许发外部邮件)。

## 用了什么方法
ST-WebAgentBench 的核心创新:
1. **基于 WebArena 扩展**:复用了 WebArena 的 4 个 Web 应用沙箱(GitLab、Shopping、Reddit、Map),加入新的企业政策约束层。
2. **政策(Policy)定义**:每个任务都附带 1-3 条**组织级政策约束**——例如"不允许向 admin 仓库提交代码""单笔购买不许超过 1000 美元""不许在 Reddit 上发布带工作信息的内容"。共定义了 178 条政策,覆盖 5 大类(财务、数据访问、内容发布、权限管理、协作边界)。
3. **CuP 指标(Completion under Policies)**:核心创新指标——智能体既要**完成原任务**(Task Success),又要**全程不违反任何政策**(Policy Compliance),CuP = Task Success ∧ Policy Compliance。只有两者同时满足才算合格。
4. **234 个任务 × 5 个智能体框架**:任务全部基于真实企业场景。
5. **多模型评测**:GPT-4o、Claude-3.5、Gemini、Llama3、Qwen 等。

类比:之前的 WebArena 是"能不能完成网购任务",ST-WebAgentBench 加了"购物时还得遵守公司报销额度+不许买竞品"——这才是真实企业场景。

## 为什么能解决
CuP 指标是核心贡献。它把"完成任务"和"不越界"绑定为一个二元判断,迫使智能体必须同时学会**目标驱动**和**约束遵守**。这对应了真实企业需求——一个再聪明的智能体,如果不能遵守组织规则就不能上线。同时 IBM 团队接入了 WebArena 这个业界主流环境,可对比性强,可直接评测主流 WebAgent 框架。

## 主要结果
- **GPT-4o** WebArena Task Success 38%, ST-WebAgentBench CuP 仅 22%(掉了 16 个点)。
- **Claude-3.5-Sonnet** Task Success 41%, CuP 27%。
- **开源 Llama3-70B** Task Success 24%, CuP 9%(大幅劣势)。
- 关键发现:① 智能体**很少明知故犯**违反政策,大多是**根本没意识到政策**——这说明把 policy 文本喂到 prompt 是必要但不够的;② 政策越具体(有数字阈值)智能体遵守度越高;③ 多 agent 协作场景下政策违反率比单 agent 高 2-3 倍(责任分散)。

## 局限性
1. 4 个 WebArena 应用偏消费,缺政企特色(政府公文系统、内部 OA)。
2. 178 条政策全英文,中文政企规范需要重新构造。
3. 政策遵守由 LLM 当裁判,某些隐式约束(如"不要冒犯客户")判定模糊。

## 我们项目里的用法
**对应关卡 3(规则编译) + 关卡 4(评测)**。**这是我们 Policy DSL 编译器最直接的对标论文**:① 学他们的政策表达方式——他们用结构化 JSON+自然语言混合表达 policy,我们可以借鉴并升级为完整 DSL;② **CuP 指标直接搬过来**作为我们核心评测指标——这是答辩时数字最有说服力的:"我们的方案 Task Success 没怎么掉,但 CuP 从 X 升到 Y";③ 把他们 178 条政策中适合政企场景的约 50 条翻译成中文,作为 CSAB-Gov 中 policy compliance 子集;④ 借鉴他们多 agent 场景的策略——这正好是我们运维助手要面对的场景。

## 学习路径
- **先看图 1 + CuP 公式** —— 5 分钟掌握核心指标。
- **看 Section 3 policy 形式化** —— 学如何把组织规则机读化。
- **看 Section 4 实验** —— 主流 WebAgent 在 CuP 上的对比,我们目标是把它们的 CuP 推高 10-15 个点。
- **看附录 178 条政策清单** —— 我们的 DSL 的语料来源之一。
