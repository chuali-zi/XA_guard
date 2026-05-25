# 方向 2:工具调用安全约束与审批 —— 文献库总览

> 本目录是参加中国雄安集团"政企智能体安全研究"比赛(XA-202620)文献库的方向 2 分目。所有论文按子方向分类,每篇配中文解读 md。

## 一句话定位

**这是我们项目的"重点方向"**——题目要求"工具调用安全约束与审批控制",对应我们 6 关卡架构中的关卡 2(办事大厅 / 规划)、关卡 3(规则编译)、关卡 5(沙箱)三个核心环节。本方向的工程化和创新空间最大、最容易出可视化效果、最易讲解给评委,是我们答辩主战场。

## 工具调用安全的 4 层防护范式(导读)

工业界 + 学术界经过 2023-2025 三年探索,已形成"四层防护"的共识架构。从 LLM 输入到工具执行,危险信号可以在四个不同时机被拦截:

```
[用户输入] → [Layer A 入口] → [Layer B 规划] → [Layer C 中间策略] → [Layer D 沙箱] → [真实世界]
```

### Layer A — 模型层(入口防御)
**做什么**:在 prompt 进入主 LLM 前做检测/改写,阻止已知 jailbreak / prompt injection 模式。
**代表方案**:Meta PromptGuard 2、Llama Guard 3、StruQ/SecAlign(微调对齐)。
**特点**:成本低(分类器或微调),但是"治标"——攻击进化它就失效。
**我们的用法**:复用 PromptGuard 2 做中文微调,作为最外层第一道关。

### Layer B — 规划层(行为对齐)
**做什么**:在 LLM 决定调用哪些工具前,对计划做合规性检查,违反则要求重新生成或转 HITL。
**代表方案**:TrustAgent(EMNLP'24, Agent Constitution + 三段嵌入)、Plan-and-Execute 架构、Reflexion 自我评判。
**特点**:让 LLM 自己写更安全的计划,但仍依赖模型自觉。
**我们的用法**:实现中文版 Agent Constitution,把等保 2.0 / GB/T 45654 编为 17-30 条原则注入 system prompt。

### Layer C — 中间策略层(我们的核心创新区) ★★★★★
**做什么**:在 LLM 决定 → 工具执行 之间插入独立的"策略引擎",做强制的规则检查、信息流追踪、隔离判断。**这一层是与"信任 LLM"解耦的——LLM 出了问题,这一层仍能拦下来**。
**代表方案**:
- **CaMeL**(双 LLM + IFC,DeepMind 2025)—— 架构层防御的标杆
- **IsolateGPT/SecGPT**(Hub-Spoke 隔离, NDSS 2025)—— 系统隔离的标杆
- **AgentSpec**(DSL 风格规则, ICSE 2026)—— 工程化规则引擎
- **ShieldAgent**(Markov Logic 形式化, ICML 2025)—— 可解释推理
- **GuardAgent**(代码化 guard, 2024)—— 外部看守模式
- **Conseca**(任务级即时 policy, HotOS 2025)—— 动态规则生成思路
- **TrustAgent**(EMNLP'24)—— 三段嵌入
- **VeriGuard**(2025)—— 形式化验证终极版

**我们的核心创新**:中文 Policy DSL 编译器 + 三色信息流污点(公开/内部/机密) + Hub-Spoke 隔离的本土化整合。

### Layer D — 沙箱层(执行隔离)
**做什么**:即使前面三层都被绕过,工具实际执行的副作用也限制在可控范围——隔离文件系统、网络、内存、进程。
**代表方案**:
- **gVisor**(Google,用户态内核 syscall 拦截)
- **Firecracker**(AWS,轻量 microVM)
- **WebAssembly**(浏览器/边缘标准沙箱)
- **CELLMATE**(2025,浏览器智能体 HTTP 流量拦截沙箱)
- **Meta CodeShield**(代码静态检查,LLM 输出前过滤)

**我们的用法**:gVisor 跑现有运维工具,WASM 跑自研 Policy 引擎,CodeShield 检查 LLM 生成的脚本。

---

## 论文一览表

### 子目录 2.1 评测基准与红队(7 篇)

| 简称 | 中文标题 | 年份 | 会议/期刊 | 难度 |
|------|---------|------|---------|------|
| ToolEmu | LM 沙箱模拟器评测智能体风险 | 2024 | ICLR Spotlight | 3 |
| R-Judge | 智能体安全风险觉察评测 | 2024 | EMNLP Findings | 2 |
| Agent-SafetyBench | 全面智能体安全评测套件(中文支持) | 2024 | arXiv (清华 CoAI) | 2 |
| AgentDojo | 提示注入攻防动态环境(业界标杆) | 2024 | NeurIPS D&B | 3 |
| ToolSandbox | 有状态多轮工具使用评测 | 2024 | arXiv (Apple) | 3 |
| AgentHarm | 智能体有害性基准(UK AISI 官方) | 2025 | ICLR | 3 |
| ST-WebAgentBench | Web 智能体安全可信度评测(CuP 指标) | 2025 | ICML | 3 |

### 子目录 2.2 中间策略层(8 篇)★ 核心创新区 ★

| 简称 | 中文标题 | 年份 | 会议 | 难度 |
|------|---------|------|------|------|
| **CaMeL** ★★★ | 用设计层面击败提示注入(双 LLM + IFC) | 2025 | DeepMind | 4 |
| **IsolateGPT** ★★★ | 智能体执行隔离架构(Hub-Spoke) | 2025 | NDSS | 4 |
| AgentSpec | 可定制运行时规则约束(DSL) | 2026 | ICSE | 4 |
| ShieldAgent | 可验证安全政策推理(Markov Logic) | 2025 | ICML | 4 |
| GuardAgent | 外部看守智能体(代码化 guardrail) | 2024 | NeurIPS WS | 3 |
| Conseca | 按场景生成临时安全政策(vision paper) | 2025 | HotOS | 2 |
| TrustAgent | 智能体宪法 + 三段嵌入 | 2024 | EMNLP Findings | 2 |
| VeriGuard | 形式化验证 LLM 智能体政策 | 2025 | arXiv | 5 |

### 子目录 2.3 执行链异常检测(2 篇)

| 简称 | 中文标题 | 年份 | 会议 | 难度 |
|------|---------|------|------|------|
| SentinelAgent | 多智能体系统的图异常检测 | 2025 | arXiv | 3 |
| Pro2Guard | PCTL 概率前瞻式安全防护 | 2025 | arXiv | 4 |

### 子目录 2.4 沙箱与受限执行(1 篇 + 2 工程资源)

| 资源 | 类型 | 难度 |
|------|------|------|
| CELLMATE | 浏览器智能体 HTTP 沙箱(2025 论文) | 4 |
| CodeShield | Meta PurpleLlama 代码静态检查工具 | 2 |
| Sandbox-Tech-Comparison | gVisor / Firecracker / WASM 三种沙箱对比入门 | 2 |

---

## 必读 5 篇(若时间紧只看这几篇)

按重要程度排序,**这是我们项目的"案头书"**:

1. **CaMeL**(`2.2_middle_policy/2025-CaMeL.md`)—— 我们整个中间策略层的架构蓝本,双 LLM 设计 + IFC 思想直接复现。
2. **IsolateGPT**(`2.2_middle_policy/2025-IsolateGPT.md`)—— Hub-Spoke 隔离与用户审批 UI 设计,与 CaMeL 完美互补。
3. **AgentDojo**(`2.1_benchmarks/2024-AgentDojo.md`)—— 业界标准评测台,我们必须在它上面跑出数字。
4. **Agent-SafetyBench**(`2.1_benchmarks/2024-Agent-SafetyBench.md`)—— 中文场景最适配的评测基准,CSAB-Gov 的最佳种子。
5. **AgentSpec**(`2.2_middle_policy/2026-AgentSpec.md`)—— 中文 Policy DSL 编译器的最直接对标论文。

**配读**:LlamaFirewall(在方向 1 / 入口防御中提及,与本目录互补)、Meta CodeShield(2.4 工程资源)。

---

## 与我们 6 关卡的对应关系

我们的"政企智能体安全中台"6 关卡架构,与本方向论文的对应关系如下:

| 关卡 | 关卡名 | 主要论文支撑 |
|------|-------|-----------|
| 关卡 1 | 门口安检(入口防御) | StruQ/SecAlign(在方向 1)、TrustAgent 的 Pre-Planning |
| 关卡 2 | 办事大厅(任务规划 + HITL) | TrustAgent、Plan-and-Execute、IsolateGPT 用户审批 UI |
| **关卡 3** | **规则编译(Policy DSL 编译器)** | **CaMeL、AgentSpec、ShieldAgent、GuardAgent、Conseca** |
| 关卡 4 | 评测靶场 | AgentDojo、Agent-SafetyBench、ST-WebAgentBench、ToolEmu、R-Judge、AgentHarm |
| **关卡 5** | **沙箱(隔离办公间)** | **gVisor、WASM、CodeShield、IsolateGPT(隔离视角)、CELLMATE** |
| 关卡 6 | 审计运营 | SentinelAgent、Pro2Guard(与方向 4 论文配合) |

**核心创新关卡**:关卡 3(中文 Policy DSL + 三色信息流)和关卡 5(WASM + gVisor 双引擎沙箱)是我们差异化竞争的主战场。

---

## 共性观察 & 未填空白

读完全部 18 篇文献,我们发现现有方案有以下 **空白 / 创新空间**:

1. **中文 / 政企本土化几乎无人做**——所有英文方案都需要重新设计中文政企规则、合规对齐(等保 2.0、GB/T 45654、网信办框架)。这是我们的最大机会。
2. **多层协同少**——CaMeL 不管沙箱,gVisor 不懂智能体,各做各的。我们做"四层一体"中台是工程价值。
3. **HITL 设计粗糙**——所有方案都说"转人工审批"但没人深入设计审批 UI。这是答辩 demo 的好亮点。
4. **审计链路缺**——少有方案提供"哈希链 + 国密签名"的合规电子证据,与方向 4 衔接是工程化空白。
5. **运行时性能**——大量方案延迟翻倍,实际部署受限。我们目标:开销 < 20%(在 P-LLM + Q-LLM + DSL 组合下)。

---

## 推荐阅读顺序(给新加入的同学)

**第 1 周(背景)**:
- 看一遍 README(本文件)
- 读 ToolEmu + AgentDojo 入门智能体安全评测
- 读 IsolateGPT 入门系统隔离

**第 2 周(中间策略层)**:
- 精读 CaMeL —— 我们的架构蓝本
- 精读 AgentSpec —— 我们的 DSL 蓝本
- 配读 TrustAgent + GuardAgent + ShieldAgent

**第 3 周(评测 + 沙箱)**:
- 读 Agent-SafetyBench 准备 CSAB-Gov
- 读 ST-WebAgentBench 理解 CuP 指标
- 跑通 gVisor 和 wasmtime 各一次
- 看 Sandbox-Tech-Comparison

**第 4 周(进阶)**:
- 读 VeriGuard 了解形式化未来方向
- 读 Pro2Guard 了解前瞻式安全
- 读 SentinelAgent 了解多 agent 异常检测
- 读 Conseca 了解动态 policy 思路

---

## 维护说明

- 本目录由 2026-05-22 学生防御研究团队整理,论文截止到 2025 年 12 月。
- 若发现解读有错或新论文待加,请直接修改对应 md 文件,并在 git commit 注明 "[02_tool_security] 更新 XX"。
- 所有 PDF 均从 arXiv 公开下载,版权归原作者。
