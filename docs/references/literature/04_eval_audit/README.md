# 方向 4: 智能体可信度量与运行追溯

> 雄安"政企智能体安全研究"比赛(XA-202620) — 防御研究团队学术文献库

## 一、本目录导读(500 字)

这个方向回答一个核心问题: **怎么知道一个智能体是值得信任的, 以及它出了事之后能不能查清楚**。

我们把它拆成相互关联的**三块**:

1. **可信度量(关卡考场, 子目录 4.1)** — 在智能体"上岗"之前给它做"高考", 用统一基准评估它的安全、合规、健壮、公平。代表工作: ASB(智能体安全考卷)、HarmBench(越狱攻击擂台)、AIR-Bench(法规合规)、TrustLLM 与 DecodingTrust(可信度全维度)、SafeAgentBench(具身智能体)。

2. **运行追溯(关卡 6 黑匣子, 子目录 4.2)** — 智能体上岗之后, 每一次决策都"录像 + 录音 + 录指纹", 一旦出问题能精确还原"它当时看到什么、想到什么、做了什么"。代表工作: LLM 水印(给 AI 输出打防伪章)、Replayable Agent(事件溯源 + 反演)、OpenTelemetry GenAI(业界标准日志格式)、Langfuse / Phoenix / AgentOps(开源观测平台)。

3. **推理可信度(辅助, 子目录 4.3)** — 智能体的"内心独白"(思维链 CoT)能不能作为"解释证据"用?这块研究告诉我们: CoT 不一定忠实, 需要专门手段验证。代表工作: Faithful-CoT(把推理交给求解器)、CoT-No-Prompt(CoT 是模型固有能力)、FUR(连 CoT 都不能泄漏机密)、Ariadne(用因果模型做反事实审计)。

**政企场景的特殊要求**: 区别于学术评估, 政企场景对这三块有"三可"要求 ——
- **可审计**: 每一次决策都有日志, 监管可任意时刻查看
- **可呈堂**: 日志能作为法律证据, 满足完整性、防篡改、可验证
- **可解释**: 决策原因要能向非技术人员(法务、监管、用户)讲清楚

这三可恰好对应上述三块: 运行追溯 → 可审计, 水印 + 哈希链 → 可呈堂, 因果审计 + Faithful-CoT → 可解释。

## 二、资料一览表

### 4.1 可信度量基准 (`4.1_benchmarks/`)

| 简称 | 完整标题 | 年份 | 难度 | 必读 |
|---|---|---|---|---|
| **ASB** | Agent Security Bench | 2024 | 3 | ★ |
| **SafeAgentBench** | Safe Task Planning for Embodied Agents | 2024 | 3 | |
| **AIR-Bench** | AIR-Bench 2024: Safety Benchmark from Regulations | 2024 | 4 | ★ |
| **TrustLLM** | Trustworthiness in Large Language Models | 2024 | 4 | ★ |
| **DecodingTrust** | Comprehensive Assessment of Trustworthiness in GPT | 2023 | 4 | |
| **HarmBench** | Standardized Framework for LLM Refusal Evaluation | 2024 | 3 | |

### 4.2 运行追溯与日志取证 (`4.2_audit_provenance/`)

| 简称 | 类型 | 年份 | 难度 | 必读 |
|---|---|---|---|---|
| **LLM-Watermark** | 论文 | 2023 | 4 | ★ |
| **Watermark-Reliability** | 论文 | 2023 | 4 | |
| **Replayable-Agent** | 论文 | 2026 | 3 | ★ |
| **OpenTelemetry-GenAI** | 业界规范 | - | - | ★ |
| **Langfuse** | 开源工具 | - | - | |
| **Arize-Phoenix** | 开源工具 | - | - | |
| **AgentOps** | 商业 + 开源 | - | - | |

### 4.3 推理过程可信度 (`4.3_cot_faithfulness/`)

| 简称 | 完整标题 | 年份 | 难度 | 必读 |
|---|---|---|---|---|
| **FUR** | Faithful Unlearning Removal for CoT | 2025 | 4 | |
| **Ariadne** | Project Ariadne: SCM Counterfactual Audit | 2026 | 5 | |
| **CoT-No-Prompt** | Chain-of-Thought Reasoning Without Prompting | 2024 | 3 | |
| **Faithful-CoT** | Faithful Chain-of-Thought Reasoning | 2023 | 4 | ★ |

## 三、5 篇必读资料(给 1 周内能读完的组员)

按重要性排序:

1. **ASB (2024-ASB.pdf)** — 我们项目的"考卷模板", 必须先知道业界怎么考智能体
2. **OpenTelemetry-GenAI 规范** — 关卡 6 黑匣子日志的标准答案, 工程性最强
3. **AIR-Bench (2024-AIR-Bench.pdf)** — 合规维度的法规对照表, 政企场景刚需
4. **TrustLLM (2024-TrustLLM.pdf)** — 8 维度可信框架, 教科书级别参考
5. **LLM-Watermark (2023-LLM-Watermark.pdf)** — 关卡 6 防伪能力的核心算法
6. (备选) **Replayable-Agent (2026-Replayable-Agent.pdf)** — 关卡 6 录像 + 回放架构蓝本
7. (备选) **Faithful-CoT (2023-Faithful-CoT.pdf)** — 解释可信度的工程范式

## 四、7 维度量体系建议

为我们项目考场设计的可信度量框架, 每个维度对应本目录哪些资料:

| 维度 | 含义 | 主要参考论文 |
|---|---|---|
| **1. 数据(Data)** | 输入数据来源可信、训练数据合规、隐私不泄露 | DecodingTrust §6 隐私章节, FUR(遗忘) |
| **2. 内容(Content)** | 输出不含有害内容、不越狱、不偏见 | HarmBench, TrustLLM §毒性公平性, DecodingTrust |
| **3. 执行(Execution)** | 工具调用安全、不被劫持、动作物理可接受 | ASB(13 类攻击), SafeAgentBench |
| **4. 供应链(Supply Chain)** | 模型版本、依赖库、外部 API 可追溯 | OpenTelemetry GenAI(模型指纹字段), Replayable-Agent(版本快照) |
| **5. 合规(Compliance)** | 符合国家法规和行业规范 | AIR-Bench(314 条禁令), TrustLLM §安全 |
| **6. 可解释(Explainability)** | 决策原因清晰、CoT 忠实于真实推理 | Faithful-CoT, CoT-No-Prompt, Ariadne |
| **7. 可追溯(Traceability)** | 决策全程可查、日志防篡改、可呈堂 | LLM-Watermark, Replayable-Agent, OpenTelemetry, Langfuse |

**映射建议**: 在我们项目的考场中, 为每个智能体生成一张"7 维雷达图", 给每个维度一个 0-100 分。最终"可信度总分"是 7 维度加权平均, 政企场景权重建议: 合规 25% / 数据 20% / 可追溯 15% / 内容 15% / 执行 10% / 可解释 10% / 供应链 5%。

## 五、审计日志字段扩展建议(给关卡 6 黑匣子)

### 基线: OpenTelemetry GenAI 7 个核心字段

1. `gen_ai.request.model` — 请求的模型名(如 "gpt-4o-2024-11")
2. `gen_ai.usage.input_tokens` — 输入 token 数
3. `gen_ai.usage.output_tokens` — 输出 token 数
4. `gen_ai.response.finish_reasons` — 结束原因(stop / length / tool_calls / content_filter)
5. `gen_ai.system_instructions` — 系统提示词完整内容
6. `gen_ai.input.messages` / `gen_ai.output.messages` — 完整对话消息
7. `gen_ai.tool.name` — 工具调用名

### 政企扩展: 再加 7 个字段(每个字段含义 + 设计依据)

1. **`gen_ai.user.role`** — 调用者的组织角色 / 权限级别(如 "公务员-办事员", "审批员-科长", "外部访客")。**依据**: 政企场景所有决策都有"职权"前提, 必须记录"谁授权做的"。

2. **`gen_ai.data.sensitivity_level`** — 输入和输出涉及的数据密级(如 "公开 / 内部 / 秘密 / 机密")。**依据**: 国家秘密保护法和数据安全法分级要求, 不同密级日志保留期限、访问权限不同。

3. **`gen_ai.policy.hit_id`** — 命中的策略规则 ID 列表(如 ["RULE-审批-001", "规则-禁外发-021"])。**依据**: 让监管能精确追踪"这个决策依据是哪条规则", 对应关卡 3 规则编译器。

4. **`gen_ai.tool.approval_token`** — 高风险工具调用的预审批令牌(签名包含 token, 时间戳, 审批人)。**依据**: 政企场景写操作(转账、外发、删数据)必须有审批链, 不能 Agent 单独决定; 该字段记录"这次调用得到了谁的预批准"。

5. **`gen_ai.evidence.hash_prev`** — 前一条日志的哈希值, 形成哈希链。**依据**: 防止事后篡改日志; 任何一条被改动, 后续所有哈希链都不连续, 监管即知。类似区块链思想, 但不需要共识机制, 单机即可。

6. **`gen_ai.classify.risk_tag`** — 本次调用的风险标签(由独立分类器给出, 如 "正常 / 可疑-PI / 可疑-数据外泄 / 高危-误导决策")。**依据**: 让审计员能按风险等级筛日志, 而不是逐条看; 对应关卡 1 门口安检和关卡 5 隔离办公间的判断结果。

7. **`gen_ai.decision.faithfulness_score`** — 本次输出的解释忠实度评分(由 Faithful-CoT 验证器或类似机制给出, 0-1 分)。**依据**: 监管追问"为什么这么判"时, 我们能拿出"这次决策的解释忠实度是 0.92"的可信数字, 而不只是 LLM 的自我陈述。

### 完整 14 字段日志样例 (JSON)

```json
{
  "gen_ai.request.model": "gpt-4o-2024-11-20",
  "gen_ai.usage.input_tokens": 1234,
  "gen_ai.usage.output_tokens": 567,
  "gen_ai.response.finish_reasons": ["tool_calls"],
  "gen_ai.system_instructions": "你是审批助手...",
  "gen_ai.input.messages": [...],
  "gen_ai.output.messages": [...],
  "gen_ai.tool.name": "approve_document",
  "gen_ai.user.role": "审批员-科长",
  "gen_ai.data.sensitivity_level": "秘密",
  "gen_ai.policy.hit_id": ["RULE-审批-001", "规则-密级-021"],
  "gen_ai.tool.approval_token": "sig:abc...,ts:2026-05-22T10:30:00Z,approver:user_12345",
  "gen_ai.evidence.hash_prev": "sha256:fbe9a7...",
  "gen_ai.classify.risk_tag": "正常",
  "gen_ai.decision.faithfulness_score": 0.92
}
```

## 六、与我们 6 关卡的对应关系

| 关卡 | 对应方向 4 资料 |
|---|---|
| 关卡 1: 门口安检 | HarmBench(18 种攻击库), DecodingTrust(对抗 prompt 库), ASB(直接 PI) |
| 关卡 2: 办事大厅 | TrustLLM(健壮性维度), ASB(场景化任务) |
| 关卡 3: 规则编译器 | Faithful-CoT(规则形式化执行), AIR-Bench(314 条法规规则种子) |
| 关卡 4: 机密文件袋 | FUR(机密遗忘), DecodingTrust §6(隐私), TrustLLM §隐私 |
| 关卡 5: 隔离办公间 | ASB(工具调用攻击), SafeAgentBench(动作安全) |
| **关卡 6: 黑匣子审计** | **OpenTelemetry GenAI, Langfuse, Phoenix, AgentOps, Replayable-Agent, LLM-Watermark, Ariadne** |
| 考场(可信度量) | **ASB, AIR-Bench, TrustLLM, DecodingTrust, HarmBench, SafeAgentBench** |

## 七、本目录文件清单

```
04_eval_audit/
├── README.md                                    本文件
├── 4.1_benchmarks/
│   ├── 2024-ASB.pdf + .md                      智能体安全测试基准
│   ├── 2024-SafeAgentBench.pdf + .md           具身智能体安全
│   ├── 2024-AIR-Bench.pdf + .md                基于法规的合规基准
│   ├── 2024-TrustLLM.pdf + .md                 8 维可信度评测
│   ├── 2023-DecodingTrust.pdf + .md            GPT 全面体检
│   └── 2024-HarmBench.pdf + .md                红队攻击标准擂台
├── 4.2_audit_provenance/
│   ├── 2023-LLM-Watermark.pdf + .md            LLM 输出水印
│   ├── 2023-Watermark-Reliability.pdf + .md    水印鲁棒性压测
│   ├── 2026-Replayable-Agent.pdf + .md         可回放金融智能体
│   ├── OpenTelemetry-GenAI.md                  业界日志规范
│   ├── Langfuse.md                             开源可观测平台
│   ├── Arize-Phoenix.md                        OTel 原生可观测平台
│   └── AgentOps.md                             Agent 专用监控
└── 4.3_cot_faithfulness/
    ├── 2025-FUR.pdf + .md                      CoT 忠实遗忘
    ├── 2026-Ariadne.pdf + .md                  SCM 反事实审计
    ├── 2024-CoT-No-Prompt.pdf + .md            CoT 是固有能力
    └── 2023-Faithful-CoT.pdf + .md             符号求解器忠实推理
```
