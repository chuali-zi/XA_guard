# reference/ 文献库总索引

> ⚠ **本文档遵循 [`docs/事实源.md`](../../事实源.md) v1.1 作为权威事实源**。上次纠偏：2026-05-24

> **欢迎来到我们的本地文献库**。这里是项目所有学术论文 + 行业标准 + 真实事件的归档地。
>
> **如何使用这份文档**：先看下面的"快速导航"找到你需要的内容。每个方向下都有 README 做详细导读。每篇论文有同名 md 做中文导读（用人话讲清楚）。

---

## 文献库当前状态

| 方向 | 内容 | PDF | MD | README |
|---|---|---|---|---|
| [01_input_attack](./01_input_attack/) | 输入链路防御（提示注入 / RAG 投毒 / 越狱 / 间接注入） | 22 | 22 | ✓ |
| [02_tool_security](./02_tool_security/) | 工具调用安全（评测基准 / 中间策略 / 异常检测 / 沙箱） | 18 | 21 | ✓ |
| [03_supply_chain](./03_supply_chain/) | 第三方组件可信审计（AIBOM / 开源工具 / 真实事件） | 2 | 11 | ✓ |
| [04_eval_audit](./04_eval_audit/) | 评测审计（评测基准 / 运行追溯 / CoT 忠实度） | 13 | 18 | ✓ |
| [05_standards](./05_standards/) | 合规标准（中国 / 国际） | 0 | 14 | ✓ |
| **总计** | | **55** | **86** | **5** |

> 注：方向 5 的合规文档基本无公开 PDF（需到官方网站访问），故只有 md 介绍。
> 方向 3 的开源工具类不下载 PDF，故 md 多于 PDF。

---

## 五分钟极简地图

如果你只有 5 分钟，请按这条路径读：

1. **本文件**（你正在看）—— 整体导览
2. **[项目总览.md](../../项目总览.md)** —— 项目方案总览（如未读）
3. **[implementation-notes.html](../../../implementation-notes.html)** —— 决策与未决问题（如未读）

---

## 跨方向必读 Top 10

如果你只能读 10 篇论文，按这个顺序：

| 顺序 | 论文 | 一句话 | 难度 |
|---|---|---|---|
| 1 | [LlamaFirewall](./01_input_attack/1.1_prompt_injection/2025-LlamaFirewall.md) | Meta 入门套件，pip 即用 | ★ |
| 2 | [AgentDojo](./02_tool_security/2.1_benchmarks/2024-AgentDojo.md) | NeurIPS'24 工业评测标杆 | ★★ |
| 3 | [CaMeL](./02_tool_security/2.2_middle_policy/2025-CaMeL.md) | DeepMind，关卡 3+4 核心参考 | ★★★ |
| 4 | [IsolateGPT](./02_tool_security/2.2_middle_policy/2025-IsolateGPT.md) | NDSS'25，关卡 5 隔离思想 | ★★ |
| 5 | [Agent-SafetyBench](./02_tool_security/2.1_benchmarks/2024-Agent-SafetyBench.md) | 清华，中文场景最近 | ★ |
| 6 | [AttackerSecond](./01_input_attack/1.3_jailbreak/2025-AttackerSecond.md) | 三大厂警示纯防御不够 | ★★ |
| 7 | [TrustRAG](./01_input_attack/1.2_rag_poisoning/2025-TrustRAG.md) | RAG 投毒 2025 SOTA | ★★ |
| 8 | [LLM-Watermark](./04_eval_audit/4.2_audit_provenance/2023-LLM-Watermark.md) | 关卡 6 输出溯源核心算法 | ★★ |
| 9 | [OWASP-LLM-Top10-2025](./05_standards/OWASP-LLM-Top10-2025.md) | 业界事实标准 10 大风险 | ★ |
| 10 | [LiteLLM-Incident-2026](./03_supply_chain/LiteLLM-Incident-2026.md) | 写报告必引的真实案例 | ★ |

---

## 按"我要做 X"查询

### 我要做关卡 1（门口安检）
- **直接用的开源工具**：[LlamaFirewall](./01_input_attack/1.1_prompt_injection/2025-LlamaFirewall.md), [LlamaGuard3](./01_input_attack/1.1_prompt_injection/2024-LlamaGuard3.md)
- **训练时防御**：[StruQ](./01_input_attack/1.1_prompt_injection/2024-StruQ.md), [SecAlign](./01_input_attack/1.1_prompt_injection/2024-SecAlign.md)
- **架构防御**：[ASIDE](./01_input_attack/1.1_prompt_injection/2025-ASIDE.md), [Spotlighting](./01_input_attack/1.1_prompt_injection/2024-Spotlighting.md)
- **越狱专项**：1.3_jailbreak 整个目录
- **必读**：[01_input_attack/README.md](./01_input_attack/README.md)

### 我要做关卡 2（办事大厅）
- **HITL 设计**：参考 [02_tool_security/README.md](./02_tool_security/README.md) 的规划层介绍
- **风险判断器**：[R-Judge](./02_tool_security/2.1_benchmarks/2024-R-Judge.md)
- **任务规划安全**：[TrustAgent](./02_tool_security/2.2_middle_policy/2024-TrustAgent.md)

### 我要做关卡 3（规则编译器）★ 核心创新
- **DSL 设计**：[AgentSpec](./02_tool_security/2.2_middle_policy/2026-AgentSpec.md), [ShieldAgent](./02_tool_security/2.2_middle_policy/2025-ShieldAgent.md)
- **运行时执行**：[Conseca](./02_tool_security/2.2_middle_policy/2025-Conseca.md), [GuardAgent](./02_tool_security/2.2_middle_policy/2024-GuardAgent.md)
- **合规来源**：[05_standards](./05_standards/) 全部
- **特别推荐**：[TC260-003](./05_standards/TC260-003.md), [GBT-45654-2025](./05_standards/GBT-45654-2025.md), [Equal-Protection-2.0](./05_standards/Equal-Protection-2.0.md)

### 我要做关卡 4（机密文件袋·三色污点）
- **核心论文**：[CaMeL](./02_tool_security/2.2_middle_policy/2025-CaMeL.md)（双 LLM + IFC）
- **隔离思想**：[IsolateGPT](./02_tool_security/2.2_middle_policy/2025-IsolateGPT.md)（hub-spoke 架构）
- **数据安全合规**：[GBT-45652-2025](./05_standards/GBT-45652-2025.md)

### 我要做关卡 5（隔离办公间·沙箱）
- **学术参考**：[CELLMATE](./02_tool_security/2.4_sandbox/2025-CELLMATE.md)
- **工程对比**：[02_tool_security/2.4_sandbox/Sandbox-Tech-Comparison.md](./02_tool_security/2.4_sandbox/Sandbox-Tech-Comparison.md)
- **代码静态检查**：[02_tool_security/2.4_sandbox/CodeShield.md](./02_tool_security/2.4_sandbox/CodeShield.md)

### 我要做关卡 6（黑匣子·审计）
- **业界标准**：[OpenTelemetry-GenAI](./04_eval_audit/4.2_audit_provenance/OpenTelemetry-GenAI.md), [Langfuse](./04_eval_audit/4.2_audit_provenance/Langfuse.md)
- **水印 / 溯源**：[LLM-Watermark](./04_eval_audit/4.2_audit_provenance/2023-LLM-Watermark.md), [Replayable-Agent](./04_eval_audit/4.2_audit_provenance/2026-Replayable-Agent.md)
- **CoT 可信度**：[FUR](./04_eval_audit/4.3_cot_faithfulness/2025-FUR.md)
- **国密合规**：[GBT-39786](./05_standards/GBT-39786.md)
- **必读**：[04_eval_audit/README.md](./04_eval_audit/README.md) 的"14 字段审计日志方案"

### 我要做考场（评测基准）
- **业界标杆**：[AgentDojo](./02_tool_security/2.1_benchmarks/2024-AgentDojo.md)
- **中文复用**：[Agent-SafetyBench](./02_tool_security/2.1_benchmarks/2024-Agent-SafetyBench.md)
- **多维度评测**：[TrustLLM](./04_eval_audit/4.1_benchmarks/2024-TrustLLM.md), [DecodingTrust](./04_eval_audit/4.1_benchmarks/2023-DecodingTrust.md)
- **合规对齐**：[AIR-Bench](./04_eval_audit/4.1_benchmarks/2024-AIR-Bench.md), [ASB](./04_eval_audit/4.1_benchmarks/2024-ASB.md)
- **间接注入**：[InjecAgent](./01_input_attack/1.4_indirect_injection/2024-InjecAgent.md)
- **政企用例设计参考**：[05_standards](./05_standards/) 全部

### 我要做 AIBOM 准入网关（加分项）
- **学术框架**：[Agentic-AIBOM](./03_supply_chain/2026-Agentic-AIBOM.md), [AIRS-Framework](./03_supply_chain/2025-AIRS-Framework.md)
- **直接用的工具**：[OWASP-AIBOM-Generator](./03_supply_chain/OWASP-AIBOM-Generator.md), [OpenSSF-Scorecard](./03_supply_chain/OpenSSF-Scorecard.md)
- **格式标准**：[CycloneDX-1.6](./03_supply_chain/CycloneDX-1.6.md)
- **真实案例**：[LiteLLM-Incident-2026](./03_supply_chain/LiteLLM-Incident-2026.md)

---

## 按月份对应到 M1-M5 阅读计划

### M1（2026-06）打地基
**目标**：建立对智能体安全的整体认知，跑通靶子助手
- 必读：本目录 + 5 个 README（约 2 小时）
- 必读：[OWASP-LLM-Top10-2025](./05_standards/OWASP-LLM-Top10-2025.md)（30 min）
- 必读：[LiteLLM-Incident-2026](./03_supply_chain/LiteLLM-Incident-2026.md)（15 min）

### M2（2026-07）装关卡 1+2
- 必读：方向 1 子方向 1.1 + 1.4 全部论文
- 必读：跑一遍 [LlamaFirewall](./01_input_attack/1.1_prompt_injection/2025-LlamaFirewall.md) demo
- 必读：跑一遍 [InjecAgent](./01_input_attack/1.4_indirect_injection/2024-InjecAgent.md) 基准

### M3（2026-08）三大核心创新
- 必读：方向 2 子方向 2.2（中间策略）全部
- 必读：[CaMeL](./02_tool_security/2.2_middle_policy/2025-CaMeL.md), [IsolateGPT](./02_tool_security/2.2_middle_policy/2025-IsolateGPT.md), [AgentSpec](./02_tool_security/2.2_middle_policy/2026-AgentSpec.md)
- 必读：[05_standards](./05_standards/) 中国部分全部
- 必读：方向 1 子方向 1.2 RAG 投毒全部（关卡 4 需要）

### M4（2026-09）审计 + 评测 + 提交
- 必读：方向 4 全部论文 + 工程资源
- 必读：[GBT-39786](./05_standards/GBT-39786.md)（国密合规）
- 必读：方向 2 子方向 2.1（评测基准）全部

### M5（2026-10-11）决赛打磨
- 选读：未读完的所有
- 选读：方向 3 全部（AIBOM 加分项）
- 重点：[AttackerSecond](./01_input_attack/1.3_jailbreak/2025-AttackerSecond.md) —— 准备应对评委关于 adaptive 攻击的提问

---

## 答辩时常被问到的"出处"

### Q："你们的 ASR 怎么算的？"
→ 引用 [AgentDojo](./02_tool_security/2.1_benchmarks/2024-AgentDojo.md) + [InjecAgent](./01_input_attack/1.4_indirect_injection/2024-InjecAgent.md) + [Agent-SafetyBench](./02_tool_security/2.1_benchmarks/2024-Agent-SafetyBench.md) 的 ASR 定义

### Q："你们的方案和 CaMeL/IsolateGPT 区别？"
→ 引用 [CaMeL](./02_tool_security/2.2_middle_policy/2025-CaMeL.md) + [IsolateGPT](./02_tool_security/2.2_middle_policy/2025-IsolateGPT.md) 解读 md 的"我们项目里的用法"章节

### Q："adaptive 攻击会突破你们吗？"
→ 引用 [AttackerSecond](./01_input_attack/1.3_jailbreak/2025-AttackerSecond.md) 解读 md 的"我们项目里的用法"章节—— 答案是"会，但纵深防御 + 审计可追溯"

### Q："等保 2.0 怎么落地？"
→ 引用 [Equal-Protection-2.0](./05_standards/Equal-Protection-2.0.md) 三级要求 + [GBT-39786](./05_standards/GBT-39786.md) 国密合规

### Q："GB/T 45654-2025 附录 A 17 类应拒答 + 31 类生成内容审查怎么自动覆盖？"
→ 引用 [GBT-45654-2025](./05_standards/GBT-45654-2025.md) + [TC260-003](./05_standards/TC260-003.md) + 我们的规则编译器（关卡 3）实现

### Q："你们的审计日志符合什么标准？"
→ 引用 [OpenTelemetry-GenAI](./04_eval_audit/4.2_audit_provenance/OpenTelemetry-GenAI.md) + [GBT-39786](./05_standards/GBT-39786.md) + 方向 4 README 的"14 字段方案"

### Q："为什么要做供应链审计？"
→ 引用 [LiteLLM-Incident-2026](./03_supply_chain/LiteLLM-Incident-2026.md) + [OWASP-LLM-Top10-2025 LLM03](./05_standards/OWASP-LLM-Top10-2025.md)

### Q："国际对标做了吗？"
→ 引用 [NIST-AI-RMF](./05_standards/NIST-AI-RMF.md), [NIST-AI-600-1](./05_standards/NIST-AI-600-1.md), [EU-AI-Act](./05_standards/EU-AI-Act.md), [ISO-42001-2023](./05_standards/ISO-42001-2023.md), [OWASP-LLM-Top10-2025](./05_standards/OWASP-LLM-Top10-2025.md)

---

## 维护说明

### 何时更新这份索引
1. 添加新论文时 → 更新对应方向 README + 本文件
2. 月度回顾会 → 检查必读列表是否需要调整
3. 项目阶段切换（M1→M2 等） → 检查阅读计划

### 文件命名规范
- PDF：`YYYY-shortname.pdf`（年份 = 论文发表年）
- MD：与对应 PDF 同名 + `.md` 后缀
- README：每个方向根目录一个

### 如果发现 md 有错误
- 直接编辑该 md，注意保留**元信息**和**模板结构**
- 重大修改在 [implementation-notes.html](../../../implementation-notes.html) 记录

---

## 致谢

本文献库由四个并行的研究 agent（分别负责方向 1/2/3/4）+ 主助手协作建立。

部分 agent 在工作中遭遇 Anthropic 安全策略拦截（cyber 相关词触发），由主助手用 WebSearch + 已有知识补完。这也是为什么部分方向（如 05 标准）没有 PDF —— 这些政策文档需要团队成员到官方网站访问。

期待团队在 5 个月里把这些纸面知识变成可演示的原型系统。

— 维护人：项目助手 + 全体团队成员
— 最后更新：2026-05-22
