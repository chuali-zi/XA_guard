# Llama Guard: Meta 的输入输出安全分类器 (Llama Guard: LLM-based Input-Output Safeguard for Human-AI Conversations)

## 元信息
- **作者机构**: Meta AI (Hakan Inan 等)
- **年份 · 发表**: 2023 · arXiv (后被 NeurIPS Workshop 接收)
- **arXiv**: https://arxiv.org/abs/2312.06674
- **本地 PDF**: ./2023-LlamaGuard.pdf
- **代码**: https://huggingface.co/meta-llama/LlamaGuard-7b
- **难度**: 2/5

## 一句话总结
用一个微调过的 Llama 模型当"内容安检员"，对输入/输出做多维度分类（暴力、仇恨、犯罪等），不安全就拦截。

## 解决什么问题
LLM 服务上线后会面对两个方向的威胁：(1) 用户输入有害内容（恶意提示、违法请求）；(2) 模型自己输出有害内容（被诱导/幻觉产生的危险信息）。

之前业界做这件事主要靠：
- **关键词黑名单**：召回率极低，攻击者改个说法就绕过
- **OpenAI Moderation API**：闭源、英文为主、不支持自部署
- **PerspectiveAPI 等老古董**：分类粒度粗、对最新攻击形态无效

Meta 需要一个**开源、可微调、可自部署、覆盖多维度**的安全分类器，能塞在 LLM 应用的输入/输出端做守门员，这就是 Llama Guard。

## 用了什么方法
**核心打比方**：在 LLM 应用的进出口各装一个安检员（同一个模型，提示词不同），用一份**可写的「安全检查表」**告诉它要查哪些类别，每件物品过去都让它判一下"合规/不合规、违反第几条"。

**关键设计**：
1. **以 LLM 为分类器**：用 Llama-2-7B 作为底模微调，而不是传统的 BERT 类小分类器。优势是能处理上下文、能跟随灵活指令（"再加一类'医疗误诊'分类"只要改 prompt 不用重训）
2. **可自定义 taxonomy**：默认 6 大类（暴力/性内容/犯罪/武器/自残/仇恨），但允许用户在 prompt 里自定义增加类别，模型 zero-shot 也能识别
3. **同一模型，双向使用**：对用户输入用 `prompt classification` 模式；对模型输出用 `response classification` 模式。两种模式共享底模，差异只在 prompt 模板
4. **训练数据**：约 13K 标注数据，覆盖 Anthropic HH 数据集、Meta 内部红队数据等

**与之前方法的区别**：
- vs Moderation API: 开源、可微调、可自部署
- vs 关键词：理解上下文（"我想做炸弹"在化学课语境下是合法的）
- vs 通用 LLM 自我审查：专门微调、更专注、推理快

## 为什么能解决
关键直觉：**安全审核本质是一个分类任务**。用 LLM 做分类器比用 BERT 强，因为它能：(1) 理解长上下文和意图；(2) 接受外部传入的分类规则；(3) 输出可解释的违规理由。Llama Guard 实际是把"内容审核"这件事完全 LLM 化、可编程化。

**何时会失效**：
1. 自适应攻击者构造 jailbreak 让 Llama Guard 本身也被绕过（jailbreak the guard）
2. 多模态内容（图片/音频）不支持，得用 Llama Guard 3 Vision
3. 长上下文里的"局部有害片段"可能被稀释

## 主要结果
- 在 OpenAI Moderation 测试集上 F1 = **0.92**（接近 GPT-4 的 0.93）
- 在 ToxicChat 测试集上 F1 = 0.74（比基线高 12 个点）
- 自定义 taxonomy zero-shot 性能也很好（不用重训就能加新类别）
- 推理延迟：7B 模型在 A100 上 < 100ms
- 模型 + 代码 + 训练数据全部开源

## 局限性
1. 7B 模型成本对小团队仍偏高（后续 Llama Guard 3 推出 8B 和 1B 版本）
2. 主要训练数据是英文，中文政企场景需要自己微调
3. 对**间接注入**（隐藏在 RAG 内容里的攻击）效果有限，需配合 Spotlighting / StruQ
4. 自身可被 jailbreak（如 GCG 攻击 Llama Guard）

## 我们项目里的用法
**对应关卡**：第 1 关「输入安检门 PromptGuard」+ 第 6 关「输出审查」。
- **直接复用**：把 Llama Guard 3 1B（轻量版）部署为输入侧 + 输出侧的双向分类器
- **中文微调**：用 200-500 条政企场景中文数据做 LoRA fine-tune，覆盖：等保 2.0 敏感操作、GB/T 45654 数据安全 9 类、TC260-003 安全治理框架要点
- **演示价值**：可以在 demo 里展示"未过 Llama Guard / 过 Llama Guard"两条线对同一恶意输入的不同反应，直观且容易讲
- **与方向 4 联动**：所有 Llama Guard 拦截事件落 Provenance-OTel 日志、上 hash 链，作为审计证据

## 学习路径
- **5 分钟版**：看 Section 3.2「Safety Risk Taxonomy」 + Figure 2（架构图）
- **30 分钟版**：Section 3 全部 + Section 4 实验
- **跳过**：训练数据细节可以略读
- **关键图**：Figure 2 工作流、Table 4 与 baseline 对比
- **配套阅读**：Llama Guard 3（最新版本，本文之后会读）、LlamaFirewall（把 Llama Guard 整合进更大系统）
