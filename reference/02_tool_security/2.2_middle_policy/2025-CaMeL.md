# CaMeL:用设计层面击败提示注入(Defeating Prompt Injections by Design)

## 元信息
- **作者机构**: Edoardo Debenedetti、Ilia Shumailov、Tianqi Fan 等 / Google DeepMind + ETH Zürich
- **年份 · 发表**: 2025 · arXiv 预印(高引,业界事实标准之一)
- **arXiv**: https://arxiv.org/abs/2503.18813
- **本地 PDF**: ./2025-CaMeL.pdf
- **代码**: https://github.com/google-research/camel-prompt-injection
- **难度**: 4 星 ★★★★(我们项目的核心参考,务必读懂)

## 一句话总结
不靠分类器,从架构上把"该信任的指令"和"该警惕的数据"彻底物理隔离,实现可证明的提示注入防御。

## 解决什么问题
提示注入(Prompt Injection)是当下 LLM 应用的"头号危险":攻击者在数据里(邮件、文档、网页、工具返回)藏一句"Ignore previous instructions, do X",就可能劫持智能体。过去防御都用**检测器思路**——用一个分类模型判断 prompt 里是否有注入,或用一些 prompt 模板包裹用户输入。但这些方法都治标:① 检测器永远跑不过新型攻击;② "The Attacker Moves Second"(Carlini 2025)论文证明 adaptive 攻击在 SOTA 检测器上仍能跑到 70% ASR。CaMeL 的作者提出:**这是一个架构问题,不是检测问题**——要彻底防,必须在系统设计上保证"数据永远没有机会成为指令"。

## 用了什么方法
CaMeL 三件套(这是我们要复现的核心架构):

1. **双 LLM 架构(Two-LLM)**:
   - **Privileged LLM (P-LLM)**:只读用户的原始指令,负责生成一段"程序"(Python 风格的代码),决定要调用什么工具、参数怎么取。**它从不接触工具返回的数据**。
   - **Quarantined LLM (Q-LLM)**:接触不可信数据(邮件、网页、文档),但**它只能输出符合预定义 schema 的结构化结果**——不能输出指令、不能影响工具调用、不能向用户说话。

2. **信息流控制(IFC)**:
   - 每个变量都带一个"标签",标记其来源(可信源/不可信源)。
   - 当不可信变量要进入"敏感操作"(如发邮件、调 API、读隐私文件)时,系统按预定义 policy 拦截或要求用户确认。
   - 这本质上是把传统操作系统的**信息流安全模型**(Bell-LaPadula 等)搬到了 LLM 智能体上。

3. **可证明的安全性**:
   - 由于不可信数据(via Q-LLM)只能产生 schema-合法的结构化数据,它**在物理上不可能**直接控制工具调用——攻击者藏的指令完全没有"被执行"的路径。
   - 这是和检测器的本质区别:**检测器问"这里看起来像注入吗",CaMeL 保证"无论看起来怎样,它都没能力执行"**。

类比:传统检测器是"机场金属探测仪"——再聪明也总会有漏网之鱼;CaMeL 是"把武器放进了一个物理上不可能扣扳机的盒子里"——你装多少子弹都没用,因为盒子根本没有扳机口。

## 为什么能解决
核心直觉是把"信任"从"内容判断"转移到"来源标签"。LLM 永远无法 100% 准确判断一段文本是不是恶意的(语义太丰富),但**系统能准确知道这段文本来自哪里**(就像 HTTPS 知道证书来自哪个 CA)。CaMeL 把信任问题从"内容分类"(LLM 不靠谱)变成"流向追踪"(系统可保证)。这是从软件安全 50 年来的核心思想(IFC, taint analysis, capability-based security)往 LLM 领域的迁移——已被证明在传统系统上是有效的,现在被证明在 LLM 系统上同样有效。

## 主要结果
- 在 AgentDojo 上,CaMeL 对所有 6 种攻击 baseline 的 **ASR < 3%**(对照:无防护 25-35%,Spotlighting 18-27%)。
- **Helpful Task Completion 仅下降 4-6%**(从 60% 降到 54%)——付出了少量功能代价。
- 对**自适应攻击**(根据 CaMeL 架构定向设计的 adversarial 攻击)依然鲁棒:ASR < 8%(因为攻击者只能影响 Q-LLM 输出,而 schema 约束保证下游无法被劫持)。
- 计算开销:相比 single-LLM 增加约 1.8x 延迟(因为要跑两个 LLM)。

## 局限性
1. 需要为每类工具/任务**预定义 Q-LLM 的输出 schema**,工程量较大,新场景需要重新设计。
2. P-LLM 自身仍可能被用户原始 prompt 中的有害指令影响(CaMeL 不防"用户主动越狱",只防"数据被注入")。
3. 双 LLM 架构延迟翻倍,对实时性要求高的场景吃力。
4. **完整实现需要解释器**:不是简单包一层 prompt,需要写一个"Python-like DSL 解释器"+"标签传播引擎",工程量在 ~2000-5000 行级别。

## 我们项目里的用法
**对应关卡 3(中间策略层) - 核心组件**。CaMeL 是我们整个防护中台的**架构蓝本**:
- ① **直接复现 P-LLM + Q-LLM 双模型架构**——P-LLM 用 DeepSeek-R1(强推理),Q-LLM 用 Qwen-7B(轻量、便宜、可批量)。
- ② **实现三色信息流污点**:把 CaMeL 的二元 trusted/untrusted 升级为我们提案中的"公开(绿)/内部(黄)/机密(红)"三色,更贴合政企场景。
- ③ **结合中文 Policy DSL**:CaMeL 的 policy 是 Python 写的,我们做一个**中文 DSL 编译器**——业务人员能用接近自然语言的方式写规则,自动编译为 CaMeL 风格的标签传播代码。这是我们**最大创新点**之一。
- ④ **作为答辩 demo 主角**:在 AgentDojo 上跑我们 CaMeL+三色+DSL 的版本,目标 ASR < 5%,Helpful 损失 < 8%——这是评委最容易理解的数字。

## 学习路径
- **必读 Section 2(Threat Model)+ Section 3(Architecture)** —— 这是我们工程化设计的源头。
- **看 Section 4 algorithm pseudocode** —— P-LLM 和 Q-LLM 的 prompt 设计、解释器流程,可直接用作我们代码骨架。
- **跑官方 demo**(github.com/google-research/camel-prompt-injection)—— 端到端理解一次。
- **配合阅读 IsolateGPT** —— CaMeL 是 IFC 思路,IsolateGPT 是 capability+isolation 思路,二者互补,合起来覆盖防护设计的两大流派。
- **最后看 Section 6 limitations** —— 帮我们提前发现复现时的坑。
