# Conseca:针对每种用途的智能体上下文安全策略(Contextual Agent Security: A Policy for Every Purpose)

## 元信息
- **作者机构**: Lillian Tsai、Eugene Bagdasarian 等 / Google
- **年份 · 发表**: 2025 · HotOS 2025(系统研究热点研讨会)
- **arXiv**: https://arxiv.org/abs/2501.17070
- **本地 PDF**: ./2025-Conseca.pdf
- **代码**: 无(短文 vision paper)
- **难度**: 2 星

## 一句话总结
HotOS 短文,提出"按场景生成临时安全政策"这一新范式——每个任务都有自己的 just-in-time 政策。

## 解决什么问题
现有所有 agent 安全方案都是**静态规则**——管理员预先写好规则,运行时执行。但智能体面临的场景千变万化:同样是"发邮件",对内部同事和对外部客户的规则就不同;同样是"读文件",在公司网内和在公共 WiFi 下规则也不同。预先写规则**永远写不全**——长尾场景太多。Conseca 提出新范式:**不要预先写规则,要为每个具体任务即时生成规则**——叫做 contextual policy。这是 vision paper,核心是讲思路而不是完整实现。

## 用了什么方法
Conseca 的核心思路(HotOS 短文只勾勒愿景):

1. **任务定义**:用户每次给智能体一个任务时,系统先问:"这个任务的目的是什么?"——把用户意图作为 policy 生成的种子。

2. **上下文感知 policy 生成**:
   - LLM(可以是同一个 agent 或独立 policy generator)根据任务+用户身份+环境状态,**临时生成一份 just-in-time 的安全政策**。
   - 例:用户说"帮我整理今天的项目报告",系统生成的 policy 包含:"可读项目目录""可写报告 doc""不可访问个人邮箱""不可发外部"。
   - 政策是一次性的——任务结束政策销毁。

3. **政策审核与执行**:
   - 临时政策需用户/管理员一次性 review(或基于"模板信任"自动通过常见类别)。
   - 执行阶段用 capability-based enforcement——只有 policy 显式 allow 的能力才能被 agent 调用。

4. **从经验中学习**:
   - 多次任务的临时政策可逐步抽象为模板,降低未来生成成本。

类比:这就是**最小授权(least privilege)的极致形式**——每次干活只给做这一件事所需的最小权限,做完立即收回。和 Unix 的 capability(POSIX capabilities)、Java permission 系统、最近的 AWS IAM 的 session token 都是同一思路。

## 为什么能解决
关键洞察:**预先写规则是 push 模式,临时生成是 pull 模式**——push 永远滞后于变化,pull 永远贴合当下。而 LLM 的能力已经足以根据任务上下文生成合理 policy 草稿,只需要人工 review 边缘情况。这种"per-task policy"在工程上是质变——它本质上让系统从"我有 100 条规则你必须遵守"变成"你这次干什么我现写规则给你"。

## 主要结果
- 这是 HotOS vision paper,**没有完整实验**——只在 2-3 个 case study 上展示思路。
- Case study:个人助理任务 / 浏览器自动化 / 数据分析任务,均能用 GPT-4 生成合理 policy 草稿。
- 计划在后续完整工作中正式评测。

## 局限性
1. **是 vision paper, 无完整实现** —— 概念好但工程挑战大。
2. 每次生成 policy 会增加显著延迟(GPT-4 调用 1-2 秒)。
3. 政策生成的正确性强依赖 LLM,容易漏判罕见风险。
4. 怎样把"任务意图"无歧义传给 policy generator 是开放问题。

## 我们项目里的用法
**对应关卡 3(规则编译)的"补充思路"**。Conseca 不会直接成为我们的主架构(短文 + 工程不成熟),但可以借鉴:
- ① **任务级 policy**——在我们的 DSL 之上加一层"按任务生成临时 policy"的机制,提升规则覆盖。
- ② **答辩亮点**:"我们的系统既支持静态规则(AgentSpec 风格)又支持任务上下文生成动态规则(Conseca 风格),实现 push+pull 双模式"——这能展示研究视野。
- ③ 实现技巧:用 DeepSeek-V2.5 做 policy generator(便宜),只在任务首次出现/上下文显著变化时调用。
- ④ 与 AIBOM 联动:每次任务的 policy 也存档,作为"行为基线"——下次同类任务可快速复用。

## 学习路径
- **5 页短文,直接全部读完** —— HotOS 文风简洁,30 分钟可读完。
- **重点看 Section 3 框架图** —— 三段式 contextual policy 流程。
- **看 Section 4 case studies** —— 三个例子直观展示。
- **不需要看实验和细节** —— 这是 vision,我们做工程化时再细化。
