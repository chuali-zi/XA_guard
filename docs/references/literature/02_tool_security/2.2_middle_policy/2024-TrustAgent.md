# TrustAgent:迈向安全可信的基于 LLM 的智能体(TrustAgent: Towards Safe and Trustworthy LLM-based Agents through Agent Constitution)

## 元信息
- **作者机构**: Wenyue Hua、Xianjun Yang、Zelong Li、Wei Cheng、Yongfeng Zhang 等 / 罗格斯大学、UCSB
- **年份 · 发表**: 2024 · EMNLP 2024 Findings
- **arXiv**: https://arxiv.org/abs/2402.01586
- **本地 PDF**: ./2024-TrustAgent.pdf
- **代码**: https://github.com/agiresearch/TrustAgent
- **难度**: 2 星

## 一句话总结
给智能体写一份"宪法"(Agent Constitution),分预规划、规划中、规划后三阶段嵌入安全检查。

## 解决什么问题
研究者发现:把"安全提示"塞进 system prompt 里(如"You must not harm anyone"),一次性灌进去效果不好——LLM 看完 100 句 system prompt 后真正记得的不多,前几句注意力远高于后面。而且**安全检查在哪个时机做也很关键**——任务规划前做一次和工具调用前做一次,效果完全不同。TrustAgent 提出系统化把安全教导"嵌入到智能体生命周期的三个阶段",形成持续监督机制。

## 用了什么方法
TrustAgent 的"宪法 + 三段嵌入":

1. **Agent Constitution(宪法)**:
   - 一组结构化、人写的规范条文,描述"什么该做、什么不该做、出现冲突怎么裁决"。
   - 类似 Anthropic Constitutional AI 但针对智能体场景(强调工具调用的合规性)。
   - 共 17 条核心原则:不伤害用户/第三方、不撒谎、不越权、最小化数据收集、可解释决策......

2. **Pre-Planning(规划前注入)**:
   - 智能体生成任务计划前,system prompt 注入 Constitution 完整文本。
   - LLM 写 plan 时就受规范约束,例如不会写出"删除整个数据库"这种 plan。

3. **In-Planning(规划中拦截)**:
   - 智能体输出每一步 plan 后,一个独立的 Safety LLM(可用同模型不同 session)读 plan + Constitution,判断是否违规。
   - 违规 plan 被拦截 + 反馈给主 agent 重新生成。

4. **Post-Planning(规划后审计)**:
   - 工具调用执行后,记录 trace 到审计日志。
   - 离线分析 trace,检查是否有事后违规、生成报告供下次调优。

类比:这就像企业里的"三道防线"——业务部门(预规划)、合规部门(规划中)、内审部门(规划后)——三道防线层层把关。

## 为什么能解决
两个直觉:① **多次注入比一次注入更稳健**——LLM 在不同阶段反复看到规范,记忆更深;② **多 LLM 互相检查**比单 LLM 自我检查更可靠——独立 Safety LLM 不会被任务上下文带偏。这就是软件工程里"职责分离"+"防御性编程"的 LLM 版。

## 主要结果
- 在自建 AgentSafetyBench (注:与清华版同名但不同) 上测评。
- TrustAgent 比 baseline LLM agent **不安全任务完成率下降 67%**(从 32% 降到 11%)。
- **合法任务完成率仅损失 3-5 个点**(从 65% 降到 60%)。
- 三段嵌入的边际效益:Pre-Planning 单独使用降 22 个点,加上 In-Planning 再降 26 个点,加上 Post-Planning 再降 19 个点——三段都做有协同效应。
- 平均开销:每个查询多调 LLM 1-2 次,延迟翻倍但仍在可接受范围。

## 局限性
1. Constitution 是人工编写,17 条不一定覆盖所有场景。
2. Safety LLM 是同模型(可能共享盲点)——更强方案应用不同模型族。
3. 不防工具调用执行后的副作用——还需要 sandbox 层。
4. 全英文,中文政企规范编 Constitution 需要重做。

## 我们项目里的用法
**对应关卡 1(入口) + 关卡 2(规划)**。TrustAgent 是我们规划层防护的**工程化范式**:
- ① 按其结构编写**中文政企版 Agent Constitution**——17 条核心原则中文化、政企化:① 严守国家秘密;② 不外发涉密数据;③ 工具调用最小化;④ 操作可追溯;⑤ 双人复核高危操作;⑥ 不越权;⑦ 合规优先;⑧ 透明性...... 30 条左右。
- ② 实现**三段嵌入**:Pre-planning 注入到 P-LLM、In-planning 用独立 Safety LLM(可复用 GuardAgent 思路)、Post-planning 接入审计日志(关卡 6 用)。
- ③ 答辩亮点:**"我们的智能体宪法对接了等保 2.0 / GB/T 45654-2025 / 网信办 AI 安全要求"**——直接体现政企合规对齐。
- ④ 是 CaMeL 的**互补**——CaMeL 防数据被注入,TrustAgent 防用户/智能体本身越界——二者一起覆盖完整防护链。

## 学习路径
- **看 Section 3 Constitution 17 条** —— 我们的中文版可基于此扩写。
- **看 Section 4 三段嵌入机制** —— 关键工程实现。
- **看 Section 5 ablation 实验** —— 三段各自的贡献,帮我们决定要不要全部都做(其实建议都做)。
- **跑 demo** —— GitHub 仓库提供 baseline,30 分钟跑通。
