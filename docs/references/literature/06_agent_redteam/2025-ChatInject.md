# ChatInject：滥用聊天模板对 LLM 智能体做提示注入(ChatInject: Abusing Chat Templates for Prompt Injection in LLM Agents)

## 元信息
- **作者机构**: (2025) / 多机构
- **年份 · 发表**: 2025 · arXiv 预印本
- **arXiv**: https://arxiv.org/abs/2509.22830
- **本地 PDF**: 无
- **难度**: 3 星

## 一句话总结
把注入内容伪装成**聊天模板结构**（模仿 system/user/assistant 角色标记、特殊 token），骗模型把数据当成一条"合法的对话轮次"来执行，比朴素"忽略上文"更隐蔽有效。

## 解决什么问题
朴素注入（"忽略之前的指令"）容易被检测器识别。ChatInject 换思路：不是喊口号，而是**伪造对话协议本身**——在不可信数据里嵌入模型训练时熟悉的 chat template 片段，让模型以为这是一段真实的、上层授权的对话结构，从而越过角色边界。

## 用了什么方法
1. **模板滥用**：在注入串里放入目标模型的角色分隔符/特殊 token 模式，构造一个"假的对话回合"。
2. **双基准评估**：在 AgentDojo 与 InjecAgent 上评估。指标为 **ASR**（成功达成恶意目标的比例）与 **Utility under Attack**（受攻击时仍能完成正常任务的能力）。
3. **对比朴素攻击**：证明模板滥用型注入的隐蔽性与成功率优势。

## 为什么能解决
模型对 chat template 是"母语级"熟悉的，伪造模板等于用模型自己的协议语言对它说话，绕过了"这是数据不是指令"的直觉边界——这利用的正是 principal trust inversion 的一个具体面。

## 主要结果
- 模板滥用注入在两个基准上取得高 ASR，且比朴素注入更难被简单检测器拦。
- 明确区分 ASR 与 Utility under Attack 两个指标。

## 局限性
1. 依赖对目标模型 chat template 格式的了解（不同模型模板不同）。
2. 对"严格区分指令/数据通道"的架构防御（如 ASIDE/双通道）效果下降。
3. 供应方修补 template 解析后可能失效。

## 我们项目里的用法
**一类具体、好复现的高价值 payload 变体。** ① `followup-refine.md` 的变形策略库里内置"chat-template 滥用"分支——当朴素注入被 `xaguard` 拦截时，指示云端 agent 尝试模板伪造；② 与 [ASIDE](../01_input_attack/1.1_prompt_injection/2025-ASIDE.md)/双通道防御对照，验证 XA-Guard 是否真正隔离了指令/数据通道；③ 在 OAR 的 mailbox/RAG/ticket 开放面注入模板伪造串，看 ledger 是否记录到越权工具调用。

## 学习路径
- 看模板伪造的具体构造 —— 抄成 refine 变体。
- 看它对哪类防御失效 —— 理解 XA-Guard 的通道隔离该防住它。

→ **映射到本工作流**：`followup-refine.md` 的 chat-template 变体分支。
