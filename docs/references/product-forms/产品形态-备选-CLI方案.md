# 备选产品形态 · CLI / SDK 方案

> **文档定位**：产品形态可行性评估的**备选方案 #2**。当前主推 MCP Server 形态，本文评估"用 CLI 或 SDK 作为主形态或补充形态"的可行性。
>
> **结论先看**：**已在三件套中合理覆盖（SDK 作为 LangChain 适配，CLI 作为评测工具 XA-Bench）。不需要额外加重。**
>
> **详细调研报告**：[./research-raw/cli-sdk-form.md](./research-raw/cli-sdk-form.md)

---

## 1. CLI / SDK 是什么

**CLI / SDK 形态**：用户（人或 agent）**主动调用**一个本地工具/库做安全检查，**不是透明拦截**（如 MCP Server 那样自动）。

两种子形态：
- **CLI**：`xa-guard scan ./session.log` — 命令行工具，开发者手动跑
- **SDK / Library**：`from xa_guard import guard` — 代码里 import，做装饰器/middleware

业界叫 **"Library/Middleware-based Guardrails"**，与"Proxy/Gateway-based"对立。

---

## 2. 业界代表产品

| 产品 | 厂商 | 形态 | 难度 |
|---|---|---|---|
| **LlamaFirewall** | Meta | 纯 Python SDK（无 CLI） | 易 |
| **Guardrails AI** | 开源社区 | Python/JS SDK + Hub | 易 |
| **NeMo Guardrails** | NVIDIA | Python SDK + Colang DSL | 中-难 |
| **Garak** | NVIDIA | CLI（红队/评测） | 易 |
| **PyRIT** | Microsoft | Python SDK（评测） | 中 |
| **阿里 AI 安全护栏** | 阿里云 | HTTPS SDK（云端） | 易 |
| **百度大模型安全护栏** | 百度智能云 | 多形态（云 SDK / 端侧 SDK / 一体机） | 易 |

**核心发现**：
- 业界主流是 **SDK 形态**（pip install + 装饰器）
- **没有纯 CLI 的运行时主形态产品**（Garak / PyRIT 都是评测工具）

---

## 3. 业界趋势：Proxy vs Library 之争

来自 2025-2026 多篇产业分析的共识：

| 维度 | Proxy/Gateway (MCP / Lakera) | Library/Middleware (LlamaFirewall SDK) |
|---|---|---|
| 部署 | Drop-in，几分钟接入 | 改代码集成 |
| 语言 | 协议中立 | SDK 绑定语言 |
| 延迟 | 多一次网络跳 | in-process，更低 |
| 可见性 | 流量层 | Agent 内部深度 |
| 策略执行 | 集中化 | 分散，细粒度 hook |
| 最适合 | **快速合规 / 多团队标准化** | **tool-call 安全 / RBAC** |

**Forrester 2025-12 提出**："Agent Control Plane"作为新市场类目——**治理层应独立于 agent 执行循环**。这暗示 **Proxy 形态在企业市场会胜出**。

**Snyk 2025 观点**：AI agent 安全会复刻 Web 安全演进路径——
- Web：从"希望没人攻击" → WAF / CSP / Middleware Security Pipeline → **Proxy/Middleware 主导**
- CI/CD：从"scan it later" → inline security gates
- API：从开放 endpoint → 速率限制 / 认证 / 输入验证

这暗示 **LLM Agent 安全会走 Proxy 主导路线**。

**多数企业实际做法**：**两者结合** — Proxy 做集中化策略 + Library 做 fine-grained tool-call 治理。

---

## 4. CLI 形态的特殊定位

**业界几乎没有"CLI 主形态"的运行时安全产品**。原因：
- AI agent 是**实时交互**的，离线 CLI 价值低
- CLI **适合 CI/CD 评测**（部署前），不适合运行时防护

**唯一合理的 CLI 应用**：评测套件（如 NVIDIA Garak / 微软 PyRIT）。

---

## 5. 政企采购倾向

| 形态 | 政企采购接受度 | 证据 |
|---|---|---|
| **SDK** | 中 | 阿里 / 百度有 SDK，但都是**配合云平台/一体机** |
| **CLI** | 低 | 政企不单独采购 CLI，作为评测工具可以 |
| **Proxy / 一体机** | **高** | 2025Q1 中标项目 1.24 亿元，**主流是平台 + 一体机**，纯 SDK 几乎不存在 |

**2025Q1 大模型平台中标盘点**：
- 百度智能云：6 个中标 / 5700 万（**端侧 SDK + 私有化一体机为主**）
- 阿里云：1400 万（云端 SaaS + 百炼平台）
- **没有纯 SDK 中标项目**

---

## 6. 假想做 "XA-Guard CLI" 或 "XA-Guard SDK 主形态"

### 6.1 做 CLI 主形态
**典型形态**：`xa-guard scan ./agent_session.log`

**问题**：
- CLI **不能做运行时防护**（事后/事前，不是实时）
- 与 Garak / PyRIT 重叠
- **政企不为单纯 CLI 买单**

**结论**：**不能作为主形态**。

### 6.2 做 SDK 主形态
**典型形态**：
```python
from xa_guard import protect

@protect(policy="enterprise-l3")
def my_langchain_agent(query):
    ...
```

**问题**：
- **与 LlamaFirewall / Guardrails AI / NeMo Guardrails 同质化严重** — 没有差异化创新
- **不能覆盖 MCP 客户端用户**（Cursor / Trae / CodeBuddy 用户没法装我们 SDK）
- **政企采购倾向"开箱即用"**，单 SDK 缺乏卖相
- **创新点失锚** — "中文 Policy DSL + 三色信息流"在 SDK 形态下退化为普通 validator

**结论**：**不能作为主形态**。

---

## 7. CLI / SDK 在三件套中的合理定位

**已经在三件套规划中合理覆盖**：

```
XA-Guard 三件套（已规划）：
├── MCP Server （主形态） ←★ 产品锚点
├── Protocol （30 页规范） ←★ 学术亮点
├── SDK （pip install） ←★ 已覆盖 LangChain / AutoGen 适配
└── XA-Bench （CLI 评测工具） ←★ 已覆盖 CLI 形态需求
```

**所以**：
- **不需要单独做"CLI 主形态"** — XA-Bench 已覆盖
- **不需要单独加重"SDK 主形态"** — Python SDK 已在三件套中作为 LangChain 适配存在

---

## 8. 客观结论

| 选项 | 评估 |
|---|---|
| CLI 替换 MCP 作为主形态 | ❌ **强烈不推荐** |
| SDK 替换 MCP 作为主形态 | ❌ **强烈不推荐** |
| CLI 作为评测工具（XA-Bench） | ✅ **已规划，继续做** |
| SDK 作为 LangChain 适配补充 | ✅ **已规划，继续做** |

### 推荐方案
**维持三件套原计划**：
- MCP Server 主形态
- SDK 作为补充（LangChain 适配）
- CLI 自然以 XA-Bench 评测套件形式存在

**不需要额外工作量调整**。

---

## 9. 与"安全外置服务"的关系

用户的原话："起一个 skill + cli 安全外置服务"。其中"**安全外置服务**"这个直觉**和 MCP Server 本质上是同一件事**：

- 自定义"外置服务"协议 = 重新发明轮子
- 用 MCP 协议做"外置服务" = 蹭整个 Anthropic + 国产 AI 工具生态

**所以我们其实已经在做"安全外置服务"**，只是用了行业标准协议（MCP），这反而是优势。

---

## 10. 与现有方案的关系

- **MCP Server**（主形态）：[产品架构.md](../../产品架构.md)
- **Skill 方案**（备选）：[产品形态-备选-Skill方案.md](./产品形态-备选-Skill方案.md)
- **外置 SaaS**（备选）：[产品形态-备选-外置SaaS方案.md](./产品形态-备选-外置SaaS方案.md)
- **横向对比 + 最终推荐**：[产品形态-对比分析.md](./产品形态-对比分析.md)

详细调研报告：[./research-raw/cli-sdk-form.md](./research-raw/cli-sdk-form.md)
