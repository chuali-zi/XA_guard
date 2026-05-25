# CLI / SDK 形态调研报告

> **调研者**：主助手（Agent R2 被 Anthropic cyber 安全策略拦截，由主助手用 WebSearch 接手）
> **调研日期**：2026-05-23
> **任务背景**：评估 CLI / SDK 形态作为 XA-Guard 产品形态的可行性

---

## 一、CLI/SDK 形态的核心定义

**CLI/SDK 形态**：用户（人或 agent）**主动调用**一个本地工具/库做安全检查，而不是依赖透明代理（如 MCP Server）自动拦截。

两种子形态：
- **CLI**：`xa-guard scan ./session.log` 这类命令行工具，开发者手动跑
- **SDK / Library**：`from xa_guard import guard` 在代码里 import，做装饰器、middleware 或显式调用

业界把这种模式叫 **"Library/Middleware-based Guardrails"**，与"Proxy/Gateway-based Guardrails"对立。

---

## 二、国际代表产品

### 2.1 Meta LlamaFirewall（SDK + Python lib，2025-05 开源）

**产品形态**：纯 Python SDK，pip 装上后在代码里 `from llamafirewall import LlamaFirewall`。

**典型用法**：
```python
from llamafirewall import LlamaFirewall, UserMessage, Role, ScannerType

firewall = LlamaFirewall(
    scanners={Role.USER: [ScannerType.PROMPT_GUARD]}
)
result = firewall.scan(UserMessage(content="..."))
```

**官方文档明确指出**：LlamaFirewall **没有专门的 CLI**——使用方式就是 Python SDK。如果想要 CLI 化部署，官方推荐用 Llama Stack 或 LlamaDeploy 把它包成服务。

**架构**：4 个 scanner（PromptGuard / AlignmentCheck / Regex / CodeShield）以 Python 类组合形式提供。

**典型集成方式**：
- 输入安检（输入到达 LLM 前调 scan）
- 输出验证（LLM 返回后调 scan）
- 工具安全（tool call 前调 scan）
- 实时监控（每次调用都记录）

**优势**：低延迟（in-process）、灵活、深度集成；**劣势**：必须改代码、SDK 锁 Python。

**来源**：[PyPI](https://pypi.org/project/llamafirewall/) / [官方文档](https://meta-llama.github.io/PurpleLlama/LlamaFirewall/)

---

### 2.2 Guardrails AI（开源 Python lib + JS lib，社区代表）

**产品形态**：Python/JS 包，主打"输出结构化验证 + 50+ 内置 validator + Hub 生态"。

**核心抽象**：`Guard` 对象 + `Validator` 组合。Pydantic 风格。

**特色**：
- 50+ 预置 validators（toxic、PII、URL valid、reading-level 等）
- 失败时可选自动纠正、重试、过滤
- 延迟 50-200ms / validator
- 支持并行 validator 执行

**典型用法**：
```python
from guardrails import Guard
guard = Guard().use(ToxicLanguage, on_fail="filter")
response = guard(llm_api=..., prompt="...")
```

**适合**：需要结构化输出 + 自定义验证规则、想本地跑全部 validator。

**来源**：[Guardrails Hub](https://hub.guardrailsai.com/) / [对比文章](https://aiagentstore.ai/compare-ai-agents/guardrails-ai-vs-nemo-guardrails)

---

### 2.3 NVIDIA NeMo Guardrails（Python lib + Colang DSL）

**产品形态**：Python 库 + 自定义 DSL（Colang，类 Python 语法的对话流定义语言）。

**核心理念**：用对话流 (dialogue rails) 控制 LLM 行为，而不仅是事后过滤。

**架构**：
- **Input rails**：输入侧拦截
- **Dialogue rails**：对话流控制
- **Output rails**：输出侧拦截
- **Execution rails**：工具执行拦截

**集成**：原生与 LangChain / LangGraph / LlamaIndex 集成，async-first。

**性能**：100-300ms / 请求（NVIDIA 硬件可降到 50-150ms）。

**劣势**：学习曲线陡（要学 Colang DSL）；NVIDIA 生态强绑定。

**来源**：[NVIDIA-NeMo/Guardrails GitHub](https://github.com/NVIDIA-NeMo/Guardrails)

---

### 2.4 Guardrails AI vs NeMo Guardrails 选型对比

业界主流共识（来自 2026 多篇对比文章）：

| 场景 | 推荐 |
|---|---|
| 结构化输出验证 | Guardrails AI |
| 多轮对话控制 | NeMo Guardrails |
| 跨多供应商编排 | 都不太够，要配代理 |
| 政企生产部署 | 两者都需要应用层集成（不是 infra 层） |

**关键限制**："It operates as a library rather than a gateway, so it requires integration at the application layer rather than the infrastructure layer."

这句是 Library 形态最大的痛点：**每个应用都要自己集成**。

---

## 三、国产代表产品

### 3.1 阿里云 AI 安全护栏（AI Guardrails）

**产品形态**：HTTP/HTTPS SDK + 与百炼 Model Studio 深度集成。

**关键特点**：
- 主打**云端 SaaS**：通过 HTTPS 调用阿里云 API
- 多语言 SDK（Java / Python）支持 HTTPS 原生调用
- 与百炼平台深度耦合（百炼是阿里大模型平台）
- 计费：按量后付费 + 资源包预付

**形态判断**：**接近 SaaS 而非纯 SDK**——SDK 只是调用云 API 的封装。

**来源**：[阿里云内容安全文档](https://help.aliyun.com/zh/document_detail/2878282.html)

---

### 3.2 百度智能云大模型安全护栏

**产品形态**：**多形态矩阵**——这是百度的差异化优势。

| 形态 | 用途 |
|---|---|
| **云端 API/SDK** | HTTP SDK + 千帆 SDK |
| **私有化部署** | 一体机 + 本地服务器，政企最关注 |
| **端侧 SDK** | X86/ARM/Linux/Android 国产化适配，离线运行 |
| **平台集成** | 百舸 AI 平台（训-推-运营一体） |

**关键亮点**（端侧 SDK）：
- 离线环境运行、无需联网
- 纯语义审核方案（终端 0 敏感词加载，降低破解风险）
- 国产化适配（信创场景）

**形态判断**：**国内最完整的多形态 LLM 安全方案**，特别是端侧 SDK 是公开工作中少见的国产化亮点。

**来源**：[百度智能云大模型安全](https://cloud.baidu.com/product/AIGCSEC/platform.html)

---

### 3.3 360 大模型安全解决方案

**产品形态**：企业级安全平台，2024-12 发布。主打"大模型安全护城河"概念，私有化部署。

---

## 四、行业趋势：Proxy vs Library 之争

来自 2025-2026 业界多篇分析的共识：

| 维度 | Proxy/Gateway（如 MCP Server / Lakera） | Library/Middleware（如 LlamaFirewall SDK） |
|---|---|---|
| **部署** | Drop-in，几分钟接入 | 改代码集成 |
| **语言** | 协议中立 | SDK 绑定语言 |
| **延迟** | 多一次网络跳 | in-process，更低 |
| **可见性** | 流量层（外部视角） | Agent 内部深度（tool call 细节） |
| **策略执行** | 集中化 | 分散，可细粒度 hook |
| **最适合** | 快速合规 / 多团队标准化 | tool-call 安全 / RBAC |

**Forrester 2025-12 提出**："Agent control plane" 作为新市场类目——治理层应**独立于 agent 执行循环**，提供独立可见性和强制执行。这暗示 **Proxy 形态在企业市场会胜出**。

**关键洞察**："We're not trying to make the LLM itself secure. Instead, we're securing the boundary between the LLM and the outside world—the tool calls."

这条边界在 Proxy 处更清晰，Library 形态需要每个应用都自己实现。

**Snyk 2025 观点**：AI agent 安全的演进路径会**复刻 Web 安全的轨迹**：
- Web 安全从 "希望没人攻击" → WAF / CSP / Middleware Security Pipeline（**Proxy/Middleware 主导**）
- CI/CD 从 "scan it later" → inline security gates
- API Gateway 从开放 endpoint → 速率限制 / 认证 / 输入验证

**这暗示 LLM Agent 安全会走 Proxy 主导路线**。

**多数企业实际做法**：**两者结合**——Proxy 做集中化策略 + jailbreak 过滤，Library 做 fine-grained tool-call 治理。

---

## 五、CLI 形态的特殊定位

纯 CLI 形态（如 `xa-guard scan ./session.log`）在业界**几乎没有主流产品**。原因：

- **AI agent 是实时交互**，离线 CLI 扫描的价值低
- **CLI 适合 CI/CD 场景**（部署前评测），不适合运行时防护
- **Garak / PyRIT 等红队工具**用 CLI——但用于评测，不是运行时防护

**结论**：纯 CLI 形态在 XA-Guard 项目里**最多作为补充工具**（如评测套件 XA-Bench 提供 CLI 接口），不能作为主要产品形态。

---

## 六、政企接受度分析

### 6.1 政企对 SDK / Library 形态的态度

**优势**：
- 可以**完全本地化**（不需要数据出企业内网）
- 可以**深度定制**
- 与现有 Python / Java 应用集成自然

**劣势（致命）**：
- **每个 agent 应用都要自己集成**——政企客户的 agent 可能用 LangChain / AutoGen / Dify / 自研，每种都要写一遍集成代码
- **无法被云厂商批量预装**——客户每次都要部署一遍
- **维护负担分散**——升级 SDK 后所有应用都要重发版

### 6.2 政企对 Proxy/Gateway 形态的态度

**优势**：
- **一次部署，所有 agent 共享**
- 与 **MCP / API 网关 / 内容审核网关** 的概念契合
- 政企已有的"统一安全网关"理念高度兼容

**劣势**：
- 网络一跳延迟
- 部署运维复杂度（要保证高可用）

### 6.3 政企采购倾向（2024-2025 中标项目盘点）

- 2025Q1 大模型平台中标 26 项 / 1.24 亿元
- 百度智能云 6 个、5700 万（**端侧 SDK + 私有化一体机为主**）
- 阿里云 1400 万（云端 SaaS + 百炼平台一体化）

**判断**：政企客户买的是**整体解决方案**（平台 + SDK + 一体机），而**不是单纯的 SDK 包**。如果我们做纯 SDK，连"被采购"的入场券都不容易。

---

## 七、对 XA-Guard 项目的可行性分析

### 7.1 如果我们做"XA-Guard SDK"

**典型形态**：
```python
from xa_guard import protect

@protect(policy="enterprise-l3")
def my_langchain_agent(query: str) -> str:
    agent = create_agent(...)
    return agent.run(query)
```

**优势**：
- 工程量较小（学习曲线低）
- 直接覆盖 LangChain / AutoGen 用户
- 与文献库中 LlamaFirewall / Guardrails AI 思路对齐

**劣势（必须诚实）**：
1. **与现有产品同质化严重**——LlamaFirewall（Meta）+ Guardrails AI 已占据主流位置，我们做的 SDK **没有差异化创新点**
2. **不能覆盖 MCP 客户端用户**（Cursor / Claude Desktop / Trae 等用户没法装我们的 SDK）
3. **政企采购倾向"开箱即用"**，单 SDK 缺乏卖相
4. **不构成"协议级"贡献**——无法对齐我们的"中文政企 Policy DSL"创新点

### 7.2 如果我们做"XA-Guard CLI"

**典型形态**：`xa-guard scan ./agent_session.log` 或 `xa-guard test-suite --policy enterprise-l3`

**优势**：
- 适合 CI/CD 集成
- 适合一次性评测
- 与 XA-Bench 评测套件天然结合

**劣势**：
- **无法做运行时防护**（CLI 是后置/事前，不是实时）
- 与现有 Garak / PyRIT 重叠
- **不能成为主产品形态**

### 7.3 在 XA-Guard 三件套中的定位

CLI / SDK **不应该是主推**，但可以作为补充：
- **XA-Guard SDK**（已经在三件套规划中）：作为 LangChain / AutoGen 适配层，扩大覆盖面
- **XA-Bench CLI**（已经在三件套规划中）：评测套件天然以 CLI 形式提供

**所以现有三件套规划已经覆盖了 CLI/SDK 的合理范围**。再单独做"CLI 主形态"或"SDK 主形态"是**重叠投资 + 失去差异化**。

---

## 八、客观结论

### 8.1 CLI/SDK 形态值不值得作为主形态？

**不值得**。理由：

1. **同质化严重**：LlamaFirewall / Guardrails AI / NeMo Guardrails 已是 SOTA，我们 SDK 形态**无法做出差异化**
2. **政企采购不接受**：政企客户买"平台/方案"不买"SDK"，纯 SDK 缺乏卖相
3. **失去 MCP 杠杆**：MCP Server 形态能覆盖所有 MCP 客户端用户（Trae / CodeBuddy / 通义灵码 / Cursor），SDK 只覆盖 LangChain 一类用户
4. **创新点失锚**：我们的核心创新——"中文政企 Policy DSL 编译器 + 三色信息流"——在 Proxy 形态下作为可视化卖点最强；在 SDK 形态下退化为"普通 validator"
5. **业界趋势相反**：Forrester / Snyk 等独立分析均判断 LLM Agent 安全会复刻 Web 安全路线，即 **Proxy/Gateway 主导**

### 8.2 CLI/SDK 形态值得作为补充吗？

**值得，但已经在三件套规划中**：
- SDK 已规划作为 LangChain 适配层
- CLI 已规划作为 XA-Bench 评测套件

**不需要额外加重 CLI/SDK 比重**。

### 8.3 给项目的明确建议

- **维持 MCP Server 为主形态**
- SDK 保持作为加分项（M5 阶段做也可以）
- CLI 自然以 XA-Bench 形式存在
- **不要为了"探索"重做产品形态**——M1 已经临近，时间宝贵

---

## 九、对用户"Skill + CLI"思路的回应

用户原话："起一个 skill + cli 安全外置服务也是个不错的选择"。

**客观回应**：

1. **"Skill"形态**：交给 Agent R1 调研（这份报告范围外）
2. **"CLI"形态**：**业界几乎没人这样做**，本质原因是 AI agent 是实时交互的，离线 CLI 价值低
3. **"安全外置服务"**：与 MCP Server 本质上是**同一形态**——MCP Server 就是一种"安全外置服务"，只是通过 MCP 协议通信

**核心洞察**：用户的"安全外置服务"直觉**和 MCP Server 是同一件事**，只是用了不同的词汇描述。所以我们其实已经在做"安全外置服务"，只不过用了行业标准协议（MCP）作为通信层，这反而是优势——比自定义协议门槛低。

---

## 关键参考来源

- [LlamaFirewall PyPI](https://pypi.org/project/llamafirewall/)
- [LlamaFirewall 官方文档](https://meta-llama.github.io/PurpleLlama/LlamaFirewall/)
- [Guardrails AI vs NeMo Guardrails 对比](https://aiagentstore.ai/compare-ai-agents/guardrails-ai-vs-nemo-guardrails)
- [NVIDIA NeMo Guardrails GitHub](https://github.com/NVIDIA-NeMo/Guardrails)
- [阿里云 AI 安全护栏](https://help.aliyun.com/zh/document_detail/2878282.html)
- [百度智能云大模型安全](https://cloud.baidu.com/product/AIGCSEC/platform.html)
- [Snyk: Future of AI Agent Security](https://snyk.io/blog/future-of-ai-agent-security-guardrails/)
- [Aembit: Agentic AI Guardrails](https://aembit.io/blog/agentic-ai-guardrails-for-safe-scaling/)
- [Forrester Agent Control Plane 2025-12]
- [LlamaFirewall arXiv 2505.03574](https://arxiv.org/pdf/2505.03574)
- [Atlan: AI Agent Risks & Guardrails 2026](https://atlan.com/know/ai-agent-risks-guardrails/)
- [Proof-of-Guardrail arXiv 2603.05786](https://arxiv.org/pdf/2603.05786)
