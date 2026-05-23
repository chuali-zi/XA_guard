# LlamaFirewall: Meta 的开源 LLM 防护整合方案 (LlamaFirewall: An Open Source Guardrail System for Building Secure AI Agents)

## 元信息
- **作者机构**: Meta AI (Sahana Chennabasappa 等)
- **年份 · 发表**: 2025-05 · arXiv
- **arXiv**: https://arxiv.org/abs/2505.03574
- **本地 PDF**: ./2025-LlamaFirewall.pdf
- **代码**: https://github.com/meta-llama/PurpleLlama (LlamaFirewall 是其中一个组件)
- **难度**: 2/5

## 一句话总结
Meta 把自家 Llama Guard / PromptGuard / CodeShield / AlignmentCheck 等防护组件打包成一个开源框架，给 Agent 应用做一站式安全防护。

## 解决什么问题
现实里要构建一个安全的 LLM Agent 应用，单一防御不够——你至少要：
1. 输入侧检测 prompt injection 和 jailbreak（PromptGuard / Llama Guard）
2. 工具/代码生成的静态扫描（CodeShield）
3. Agent 推理链的对齐审查（AlignmentCheck）
4. 输出侧的内容审核（Llama Guard）

这些组件各自开源，但**集成它们是一个大坑**：接口不一致、数据格式不互通、配置散乱、性能开销不可控。Meta 注意到社区在重复造轮子，决定**官方出一个整合框架**——LlamaFirewall。

## 用了什么方法
**核心打比方**：之前你买防火墙、入侵检测、杀毒软件、SIEM 都是不同厂商，集成是噩梦。LlamaFirewall 就像企业级 SOC 平台，把这些工具用统一的 API 封装好，开发者只需要"装上它，配几行 yaml，全套防护就到位"。

**框架包含四大模块**：
1. **PromptGuard 2**：升级版的输入端注入分类器（22M 和 86M 两种规格，比 Llama Guard 更轻量），在 1% FPR 下召回 97.5%
2. **Llama Guard 3 / 4**：内容审核（沿用前作思路，多模态可选）
3. **AlignmentCheck**：用一个 LLM 实时审查 agent 的"思考链"，看是否被劫持偏离了原任务（独家创新）
4. **CodeShield**：对 agent 生成的代码做静态扫描（如 detect-secrets、bandit、semgrep 集成），防止恶意代码执行

**关键设计**：
- **Pipeline-style API**：开发者把 LlamaFirewall 接入到 LangChain/LangGraph 的 callback 钩子，每个阶段（用户输入 → 规划 → 工具调用 → 输出）都过相应组件
- **可配置严格度**：支持 strict/balanced/permissive 三档，按场景调
- **统一日志**：所有拦截事件输出统一 JSON 格式，方便对接 SIEM/审计系统

**与之前方法的区别**：
- vs 单个 Llama Guard：LlamaFirewall 是完整 pipeline，覆盖输入→规划→输出全链路
- vs Anthropic Constitutional Classifiers：LlamaFirewall 开源、可自部署
- vs **CaMeL** (DeepMind)：CaMeL 是双 LLM 思路，LlamaFirewall 是多模块整合思路；两者可结合

## 为什么能解决
关键直觉：**单点防御都能被绕过；纵深防御才能形成防御链**。LlamaFirewall 在每个阶段都拦一道，攻击者必须同时绕过 4 道才能成功，整体安全度指数级提升。同时整合带来的标准化大幅降低开发者门槛。

**何时会失效**：
1. AlignmentCheck 本身用 LLM，仍可能被 jailbreak（"meta-jailbreak"）
2. 各组件之间的协同 latency 累计较高（每加一层延迟+10-50ms）
3. 配置不当时可能误拦（FP 率高），影响用户体验

## 主要结果
- PromptGuard 2 在 ToxicChat、Anthropic HH 等多个数据集上 F1 > 0.92
- 整体框架对 9 种常见注入/jailbreak 攻击 ASR 降幅 60-95%
- 全模块开源，licence 友好（Apache 2.0）
- 已被 LangChain、LlamaIndex、Mistral 等主流 framework 集成

## 局限性
1. 主要面向英文场景，中文需要自己微调
2. AlignmentCheck 需要一个额外的 LLM 调用，成本+50%
3. 对**自适应攻击者**（知道你用 LlamaFirewall）的防御仍待观察（见《Attacker Moves Second》）
4. 多语言/多模态支持不均衡

## 我们项目里的用法
**对应关卡**：第 1 关 + 第 6 关 + 第 7 关 (审计) 的工程底座。
- **直接复用**：把 LlamaFirewall 作为我们防护中台的"参考架构"，第 1 关用 PromptGuard 2 + Llama Guard 中文微调
- **借鉴 AlignmentCheck**：在第 2 关「规划阶段」加一个"对齐审查 LLM"，实时审查 agent 的 chain-of-thought 是否偏离原任务（这是 LlamaFirewall 的独家创新，值得搬过来）
- **借鉴 CodeShield**：在我们运维助手场景里，agent 生成的 shell 命令/Python 代码先过一道静态扫描（如 detect-secrets + 自定义规则）
- **演示价值**：方案里明确写"我们的架构借鉴 LlamaFirewall 并做了中文政企场景适配"，给评委权威背书
- **答辩**：可以引用 LlamaFirewall 论文的多模块协同设计，论证"纵深防御是必要的"

## 学习路径
- **必读**：本论文是方向 1 防护侧的最重要工程整合论文，必读
- **5 分钟版**：Figure 1（架构总览）+ Section 3 各模块简介
- **30 分钟版**：通读全文（论文不长，~25 页）
- **跳过**：可以略过具体实验数字，重点理解架构思想
- **关键图**：Figure 1（pipeline 架构）、Figure 3（AlignmentCheck 工作流）
- **配套阅读**：依次读 PromptGuard 2 → Llama Guard 3 → AlignmentCheck 论文，形成体系
- **动手**：本论文的 GitHub 仓库可直接跑通 demo，建议安装并跑一遍
