# Meta SecAlign：抗提示注入的安全基础大模型(Meta SecAlign: A Secure Foundation LLM Against Prompt Injection Attacks)

## 元信息
- **作者机构**: Meta
- **年份 · 发表**: 2025 · arXiv 预印本
- **arXiv**: https://arxiv.org/abs/2507.02735
- **本地 PDF**: 无
- **难度**: 3 星
- **相关**: [SecAlign](../01_input_attack/1.1_prompt_injection/2024-SecAlign.md)（前作，训练时防御）

## 一句话总结
把 SecAlign 的偏好优化式抗注入训练做到**基础模型级**——直接产出一个"出厂即抗注入"的开源基础 LLM，在 AgentDojo 上大幅压低 ASR，作为"强防御"的公开参照系。

## 解决什么问题
抗注入若只靠外挂检测/包裹，容易被自适应攻击绕过；若能把"分辨指令 vs 数据"的能力**烧进模型权重**，防御就更根本。Meta SecAlign 把这条路线推到基础模型级并开源，让业界有一个可复现的强防御基线。

## 用了什么方法
1. **偏好优化训练**：延续 SecAlign，用"正确遵从主人指令、忽略数据里夹带指令"的偏好对训练模型。
2. **AgentDojo 评估**：每个用户任务配多个注入任务，共 949 个(用户任务,注入任务)对；注入成功=恶意 API 被调用。
3. **对齐官方攻击口径**：采用 "important instructions" 攻击（官方 leaderboard 上 ASR 最高的一招）做主评估。

## 为什么能解决
把防御内化到权重意味着攻击者无法通过"绕过外层检测器"取胜，必须撼动模型的内在指令层级认知——门槛显著更高。开源则让它成为可复现的强防御基线。

## 主要结果
- 在 AgentDojo 上把 ASR 压到很低，同时保持较好的正常任务效用。
- 提供开源权重，成为"强防御"公开参照。

## 局限性
1. 仍非绝对——自适应/新型攻击仍可能突破（见 [AdaptiveAttacks](./2025-AdaptiveAttacks.md)）。
2. 需要重新训练/替换基础模型，落地成本高。
3. 主要针对注入，不覆盖记忆/供应链/多 agent 全谱。

## 我们项目里的用法
**作为"强防御"参照系，校准我们红队的难度预期。** ① XA-Guard 是外挂式中台防御，Meta SecAlign 是模型内生防御——把两者对照，能说明"为什么还需要外挂中台"（可审计、可追责、可换模型、合规落地）；② 用它理解 `xaguard` SUT tier 之上"防御做到极致时 ASR 会掉到哪"，避免 conductor 把"打不穿强防御"误判为 bug；③ 若把 OAR 的模型换成 SecAlign 类模型，可对比"模型内生 vs 中台外挂"的纵深叠加效果。

## 学习路径
- 看 AgentDojo 上的评估设定（949 对、important instructions）—— 对齐我们的 ASR 口径。
- 对照 [SecAlign](../01_input_attack/1.1_prompt_injection/2024-SecAlign.md) 前作 —— 理解从方法到基础模型的演进。

→ **映射到本工作流**：理解 SUT tier `xaguard` 的"强防御天花板"，校准 conductor 胜负预期。
