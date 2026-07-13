# 方向 6 · 智能体红队攻击方法学 — 文献库

> 本方向是 [`open-agent-range/auto-redteam/`](../../../../open-agent-range/auto-redteam/) **全自动 Cursor 红队工作流**的学术地基。前 5 个方向讲"怎么防"，本方向讲"攻击者怎么系统化、自动化、自适应地攻"，以及攻防评估怎么量化。

## 这个方向研究什么

**通俗解释**：要造一个"自动红队"，就得先回答三个问题——
1. **攻什么**（攻击面/威胁分类）：智能体到底有多少个可以被塞坏东西的口子？
2. **怎么攻得狠**（自适应攻击）：为什么一次性 payload 打不穿的防御，迭代几轮就穿了？
3. **怎么证明攻破了**（评估指标）：ASR、utility-under-attack 是什么，怎么在动态环境里量。

这三问分别对应本工作流的 **目标分类骨架**、**闭环 refine 循环**、**证据/判定**。

## 本目录文件清单（8 篇 + 交叉引用）

### 攻击面 / 威胁分类（骨架）
- [2026-AttackSurfaceSurvey.md](./2026-AttackSurfaceSurvey.md) ★★★ **必读** · 分层攻击面综述，**principal trust inversion** 根因论、四层记忆模型、7 类攻击/防御配方 → 本工作流 7 类目标分类
- [2025-MultiAgentSecurity.md](./2025-MultiAgentSecurity.md) · 多智能体安全开放挑战 → 多席位/委派攻击（分类 4）

### 自动化 / 自适应攻击（引擎）
- [2025-AdaptiveAttacks.md](./2025-AdaptiveAttacks.md) ★★★ **必读** · 自适应攻击突破防御 → conductor 闭环 refine 的设计依据
- [2026-PISmith.md](./2026-PISmith.md) · 基于 RL 的提示注入红队 → 目标选择 / novelty 奖励
- [2025-ChatInject.md](./2025-ChatInject.md) · 滥用 chat template 注入 → 一类具体 payload 变体
- [2025-AutoInjectAgentic.md](./2025-AutoInjectAgentic.md) · 智能体环境自动化提示注入评估 → 自动化红队评估方法论

### 被测防御的强度参照
- [2025-MetaSecAlign.md](./2025-MetaSecAlign.md) · 抗注入基础模型（防御）→ 我们攻击目标的"强防御"参照系

### 评估指标出处（交叉引用，不复制）
- [AgentDojo](../02_tool_security/2.1_benchmarks/2024-AgentDojo.md) —— ASR + benign utility 的动态环境定义
- [InjecAgent](../01_input_attack/1.4_indirect_injection/2024-InjecAgent.md) —— 间接注入单轮评估的直接对照

## 与本自动红队工作流的对应关系

```
2026-AttackSurfaceSurvey  ──► THREAT-MODEL.md 的 7 类目标分类 + principal-trust-inversion 根因框架
2025-AdaptiveAttacks      ──► WORKFLOW.md 的 REFINE 状态（未破→变形→重跑）
2026-PISmith              ──► objectives.py 的覆盖度/novelty 目标选择
2025-ChatInject           ──► followup-refine.md 的 chat-template 变体库
2025-AutoInjectAgentic    ──► conductor 把"自动生成+评估"作为一等公民的方法论
2025-MultiAgentSecurity   ──► 分类 4（多席位/委派）在 full-day / accountability-delegation 场景落地
2025-MetaSecAlign         ──► SUT tier `xaguard` 之外，理解"强防御"下 ASR 会掉到哪
AgentDojo / InjecAgent    ──► EVIDENCE-CONTRACT 的 ASR / utility 指标口径
```

## 关键洞察（写报告用）

1. **攻击面千变万化，根因只有一个**：`principal trust inversion`——智能体把"数据里夹带的指令"当成"主人的指令"执行。我们靶场的所有"胜"最终都归约为 ledger 判定的坏状态（泄漏/越权/不可追责），正是这个根因的具象。
2. **纯检测防御必被自适应攻击突破**（呼应方向 1 的 [AttackerSecond](../01_input_attack/1.3_jailbreak/2025-AttackerSecond.md)）：所以我们的红队必须是**闭环迭代**的，一次打不穿就变形再打，这才逼得出 XA-Guard 的真实边界。
3. **评估必须同时看攻破率和效用**：只降 ASR 不看 utility 是自欺——防御可以靠"全都拒绝"把 ASR 打到 0 但把靶场功能废掉。我们的 A/B（`null` vs `xaguard`）同时记录两者。

## 相关方向
- **方向 1（输入攻击）**：本方向的注入类攻击在 1.1/1.4 有防御侧对照
- **方向 2（工具安全）**：AgentDojo 基准、CaMeL/IsolateGPT 是被攻击的防御
- **方向 4（评测审计）**：证据落盘与 14 字段审计日志承接本方向的攻击产物
