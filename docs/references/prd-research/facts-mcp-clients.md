# MCP 客户端真实支持状态 - 事实源查实

> ⚠ **本调研报告已被 [`docs/事实源.md`](../../事实源.md) v1.1（2026-05-24）更新**。
>
> 当报告内容与事实源冲突时，**以事实源为准**。本报告保留作研究痕迹与原始引用，不修改正文。
>
> 主要已纠偏点（详见事实源 §7 已知错误表）：
> - 风险类目：17 类 / 29 类 / 31 类是 GB/T 45654-2025 附录 A 不同切片（**非草案 vs 国标**关系）
> - 应拒答题库：**总规模 ≥ 500 题**，每种 ≥ 20 题（340 是每类下限相加）
> - GB/T 45654-2025 标题正式为"**网络安全技术**"非"信息安全技术"
> - Lakera Guard 收购方为 **Check Point**（公告 2025-09-16 / 完成 2025-11-11），非 Cisco
> - CalypsoAI 被 F5 收购（2025-09-11 / $180M 现金）
> - Protect AI 被 Palo Alto 收购完成（2025-07-22，整合为 Prisma AIRS）
> - MCP 协议当前稳定版 **2025-11-25**，SSE 已 deprecated
> - **Qcoder 拼写错误 → Qoder**（阿里 2025-08 独立 Agentic IDE）
> - **通义灵码 2026-05-20 更名 Qoder CN**
> - **CodeGeeX 暂未在 MCP 官方客户端清单**
> - 国产 IDE elicitation 全部未声明
> - **CaMeL 归属 Google Research**（非 DeepMind）
> - **ShieldAgent 机制：概率规则电路 + 形式化验证**（非 Markov Logic）
> - **The Attacker Moves Second 数字：MetaSecAlign 96% ASR / StruQ ≈ 100%**（非 70%）
> - LiteLLM 2026-03 事件：**账号 teampcp 劫持原维护者**（非 APT campaign）

> 查询时间窗口：2026-05-23 至 2026-05-24
> 查实方法：以厂商官方文档 / modelcontextprotocol.io 官方 / PyPI 等一级源为准，必要时引用权威媒体（OSCHINA / 官方博客 / 知乎专栏）补全时间线。
> 置信度评级：**高** = 至少 2 个一级源相互印证；**中** = 1 个一级源或多个二手源相互印证；**低** = 仅二手源、信息冲突或时间不明。

---

## 总览：可宣称强度（结论先行）

| 客户端 | 真实 MCP 支持 | elicitation | 建议 PRD 用词 |
|---|---|---|---|
| Claude Desktop | 是（官方一级支持） | **不支持**（截至 2026-05） | "100% 跑通"（不含 elicitation） |
| Cursor | 是（一级，含 elicitation） | **支持**（v1.5 起，2025-08） | "100% 跑通，含 HITL 弹窗" |
| Claude Code | 是（一级，含 elicitation） | **支持** | "100% 跑通" |
| Codex (OpenAI) | 是（一级，含 elicitation） | **支持** | "100% 跑通" |
| Trae (字节) | 是（v1.3.0 起原生支持） | 未在官方 MCP 客户端列表 / 未声明 elicitation | "按版本验证（v1.3.0+）" |
| CodeBuddy (腾讯) | 是（IDE 与 CLI 双形态） | 文档未明确 elicitation | "按版本验证" |
| 通义灵码 → Qoder CN (阿里) | 是（v2.5.0 插件起） | 未声明 | "按版本验证" |
| Qoder (阿里独立 IDE) | 是（官方列入 MCP clients） | 仅声明 Tools | "按版本验证，仅 Tools" |
| 文心快码 Comate (百度) | 是（v3.5 起，2025-04） | 未声明 | "按版本验证" |
| CodeGeeX (智谱) | **不在官方 MCP 客户端列表**，未见官方 MCP 文档 | 未声明 | **不建议宣称 MCP 跑通** |

---

## 事实 1：MCP 协议当前版本

- **当前稳定版本**：`2025-11-25`（这是 modelcontextprotocol.io 当前 specification 路径所指向的版本）。该版本是协议自发布以来最大规模更新，包含 async tasks、enhanced sampling、elicitation、server-side agent loops、Client ID Metadata Documents、extensions 系统等。
- **下一版本（RC）**：`2026-07-28` 已于 2026-05-21 由 Lead Maintainers David Soria Parra 和 Den Delimarsky 宣布为发布候选版本，引入 stateless protocol core、Extensions framework、Tasks、MCP Apps、authorization 强化、形式化弃用策略。
- **1.0 / 初始发布**：协议由 Anthropic 于 2024-11 推出；Python SDK 1.0.0 于 **2024-11-25** 发布。
- **当前传输方式**（按官方 spec 2025-06-18 transports 文档）：
  - **stdio**：本地子进程标准输入输出，单用户
  - **SSE**（Server-Sent Events）：已被官方标注为**deprecated**，spec 已转向 Streamable HTTP
  - **Streamable HTTP**：当前推荐的远程传输，使用 HTTP POST/GET + 可选 SSE 流，支持多并发客户端
- **Elicitation 状态**：**已标准化**。首次出现在 2025-06-18 release，2025-11-25 release 中保留并增强。规范规定 client 可声明 form (in-band) / url (out-of-band) 两种模式，至少支持其一。仅基本类型（string/number/boolean），server 不得索取敏感信息。
- **治理变更**：2025-12 Anthropic 将 MCP 捐赠给 Linux Foundation 旗下的 Agentic AI Foundation，正式社区化治理。
- 来源：
  - https://modelcontextprotocol.io/specification/2025-11-25 （官方）
  - https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/ （官方博客）
  - https://blog.modelcontextprotocol.io/posts/2026-mcp-roadmap/ （官方博客）
  - https://modelcontextprotocol.io/specification/2025-06-18/basic/transports （官方 spec）
- 置信度：**高**

---

## 事实 2：Python `mcp` 库当前情况

- **当前版本**：`1.27.1`，发布于 **2026-05-08**（PyPI 官方页查询）
- **首个 1.0.0**：2024-11-25
- **API 稳定性**：PyPI 标注 "Development Status: 4 - Beta"，即"功能可用、未完全冻结"。每月多次发布，仍在活跃迭代。版本号已破 1.0 多个小版本，但官方未声明 1.x 稳定承诺。
- **协议版本对应**：PyPI 页面未显式标注实现的 MCP spec 版本号；按 GitHub 仓库变更日志通常滞后官方 spec 1–4 周完成跟进。
- **Python 要求**：Python ≥ 3.10，MIT 许可证
- 来源：https://pypi.org/project/mcp/ （官方一级）
- 置信度：**高**

---

## 事实 3：Cursor 当前 MCP 支持状态

- **MCP 支持**：完整，含 elicitation
- **支持的传输**：stdio + SSE + Streamable HTTP（三种全支持）
- **传输细节**（来自 cursor.com/docs/mcp）：
  - stdio：本地、单用户、Cursor 拉起子进程
  - SSE：本地或远程、多用户、URL 端点、OAuth
  - Streamable HTTP：本地或远程、多用户、URL 端点、OAuth（推荐新建项目选这个）
- **配置文件路径**：
  - 项目级：`.cursor/mcp.json`
  - 全局：`~/.cursor/mcp.json`
- **elicitation 支持**：**是**。Cursor v1.5（2025-08）起加入。
- **MCP capabilities**（官方列表）：Prompts、Tools、Roots、Elicitation、DCR
- **已知问题**：连接远程仅支持 SSE 的旧服务器时，Cursor 不会从 Streamable HTTP 优雅降级到 SSE（社区 Bug Report）
- 来源：
  - https://modelcontextprotocol.io/clients （官方 MCP 客户端清单，列出 Cursor 支持 Elicitation）
  - https://docs.cursor.com/context/mcp#protocol-support （Cursor 官方）
  - https://cursor.com/docs/mcp.md（Cursor 官方 markdown 版）
- 置信度：**高**

---

## 事实 4：Claude Desktop 当前 MCP 支持状态

- **MCP 支持**：完整（一级支持，MCP 起源宿主）
- **平台**：仅 **macOS 与 Windows**。Linux 官方不支持（截至 2026-05）。
- **配置文件路径**：
  - macOS：`~/Library/Application Support/Claude/claude_desktop_config.json`
  - Windows：`%APPDATA%\Claude\claude_desktop_config.json`
- **支持的 MCP capabilities**（来自官方 clients 页面）：Resources、Prompts、Tools、Roots、Apps、DCR
- **elicitation 支持**：**否**（官方 clients 页面未列出 Elicitation，仅在 Claude Code 中支持，Claude Desktop 暂未实现）
- **日志路径**：
  - macOS：`~/Library/Logs/Claude/mcp*.log`
  - Windows：`%APPDATA%\Claude\logs\mcp*.log`
- 来源：
  - https://modelcontextprotocol.io/docs/develop/connect-local-servers （官方）
  - https://modelcontextprotocol.io/clients （官方）
- 置信度：**高**

⚠ 注意：很多二手文章把"Claude Code"（CLI 形态，支持 Elicitation）与"Claude Desktop App"（桌面 GUI，不支持 Elicitation）混为一谈，PRD 撰写时务必区分。

---

## 事实 5：Trae（字节跳动）当前 MCP 支持状态

- **是否原生支持 MCP**：**是**。Trae IDE v1.3.0（**2025-04-21/22 发布**）正式引入 MCP 与 .rules 支持。
- **支持的传输**：**stdio + SSE**（截至 v1.3.0 公告原文，未提及 Streamable HTTP）
- **配置文件路径**：
  - 全局：`~/.cursor/mcp.json`（注意：v1.3.0 公告原文确实复用了 Cursor 的路径作为兼容兜底）
  - 项目级：`<project>/.trae/mcp.json`
  - UI 内部使用 `mcp.json` 名称，可在 IDE 里点 "原始配置 (JSON)" 编辑
- **预置入口**：内置智能体 "Builder with MCP" 自动加载所有已配置 MCP Server；也可创建自定义 Agent 绑定特定 MCP Server。
- **MCP 市场**：内置 MCP 市场，支持"轻松配置"标签的一键安装。
- **平台覆盖**：
  - macOS：v1.0 起（2025-01）
  - Windows：2025-02 末
  - Linux：官方仅声明"未来版本"支持（截至公开资料未确认上线时间）
- **价格 / 免费？**：**是**，官方明确免费。Windows 版起免费提供 GPT-4o / Claude-3.5-Sonnet 调用、Builder 模式。
- **elicitation 支持**：**未确认**。Trae 不在 modelcontextprotocol.io/clients 官方客户端列表内，官方文档未公开声明 elicitation 形态。
- **演进**：v2.0.0（2025-07-18）引入 SOLO 模式。截至 2025-08-23 共发布 63 个版本。
- 来源：
  - https://www.oschina.net/news/345886/trae-1-3-0-released （v1.3.0 发布公告，OSCHINA）
  - https://www.cnblogs.com/volcengine-developer/articles/18850201 （火山引擎开发者社区，官方关联渠道）
  - https://www.aibase.com/news/17375
- 置信度：**中**（厂商无独立官方文档站可直接 WebFetch；信息源以官方关联媒体与 v1.3.0 发布公告为主）

⚠ 重点核实：**Trae 确实原生支持 MCP**，PRD 可宣称"v1.3.0+ 原生支持"，但 **elicitation 支持需另行测试验证**，不宜在 PRD 中预设"全功能 HITL 弹窗能跑"。

---

## 事实 6：CodeBuddy（腾讯云）当前 MCP 支持状态

- **是否原生支持 MCP**：**是**。腾讯云代码助手 CodeBuddy 是"中国首批"宣称支持 MCP 协议的代码助手，2025-04 时已支持。
- **产品形态**：双形态
  - **CodeBuddy IDE**：独立 AI 代码编辑器（不是单纯插件）
  - **CodeBuddy CLI**：命令行版本，单独的 MCP 配置文档
- **支持的传输**（按官方文档）：**STDIO + SSE + HTTP streaming（三种）**
- **配置**：
  - IDE 内：通过侧边栏右上 "Settings" 按钮 → "MCP" 标签页配置
  - 支持 **JSONC**（带注释的 JSON）格式
  - 支持环境变量展开
- **MCP 市场**：腾讯生态集成（CNB、TAPD、TCA 等），30+ 开发工具
- **权限**：三级规则（Deny > Ask > Allow），不支持通配符
- **elicitation**：官方文档未明确说明（同上）
- **MCP Prompts 自动转 slash commands**：是
- 来源：
  - https://www.codebuddy.ai/docs/cli/mcp （CodeBuddy 官方文档，英文）
  - https://www.codebuddy.ai/docs/ide/User-guide/MCP （IDE MCP 配置官方）
  - https://copilot.tencent.com/docs/cli/mcp （中文版官方）
- 置信度：**高**（厂商有完整官方英中文档站）

⚠ 重点核实：**CodeBuddy 是真支持 MCP，不只是 Rules 系统**。"国产 IDE 全覆盖"中包含 CodeBuddy 是站得住脚的。

---

## 事实 7：通义灵码（阿里云）当前 MCP 支持状态

- **是否原生支持 MCP**：**是**，2025-04 阿里云灵码新增"智能体模式"时同步引入 MCP 工具支持。
- **产品形态**：IDE 插件（JetBrains + VS Code），不是独立 IDE
- **版本要求**：
  - JetBrains 插件 ≥ v2.5.0
  - VS Code 插件 ≥ v2.5.0
- **支持的传输**：STDIO + SSE；**Streamable HTTP** 于 **2025-06** 加入支持
- **MCP 市场**：深度集成"魔搭 MCP 广场"，2400+ MCP 服务
- **品牌更名**：2026-05-20 起，原"通义灵码 / Lingma"正式更名为 **Qoder CN**，文档已迁移至 Qoder CN 子产品。**这意味着 2026-05 之后 PRD 不要再用"通义灵码"作为产品名，应使用"Qoder CN"或"Lingma（原通义灵码）"。**
- **elicitation**：官方文档未明确声明
- 来源：
  - https://help.aliyun.com/zh/lingma/user-guide/guide-for-using-mcp （阿里云官方）
  - https://help.aliyun.com/zh/lingma/product-overview/changelogs-of-202504 （官方变更日志）
  - https://help.aliyun.com/zh/lingma/product-overview/changelogs-of-202506 （官方变更日志，确认 Streamable HTTP）
- 置信度：**高**

⚠ 重要：阿里云生态下 "通义灵码"（插件）与 "Qoder"（独立 IDE）是**两个产品**，详见事实 9。

---

## 事实 8：文心快码 Comate（百度）当前 MCP 支持状态

- **是否原生支持 MCP**：**是**。2025-04 升级至 v3.5 时通过 MCP 协议接入"全面兼容主流开发工具链"。
- **产品形态**：双形态
  - VSCode / JetBrains 插件
  - 独立的 Comate AI IDE
- **MCP 客户端**：Zulu 智能体作为 MCP 客户端
- **支持的传输**：**STDIO + SSE 两种**（按官方公告，截至查询时未提到 Streamable HTTP）
- **配置文件路径**：`.baidu-comate/mcp.json`（项目级）
- **项目级 MCP 启停**：是，UI 可启用/禁用每个 MCP 服务
- **elicitation**：官方文档未明确声明
- 来源：
  - https://comate.baidu.com/zh/page/6ejbrbq5tma （百度官方"MCP 与 Comate 联动配置指南"）
  - https://comate.baidu.com/zh/readme （官方使用手册）
  - https://cloud.baidu.com/doc/COMATE/s/xlnvqe047 （百度智能云产品文档）
  - https://docs.cloudbase.net/en/ai/cloudbase-ai-toolkit/ide-setup/baidu-comate （第三方，含 mcp.json 路径示例）
- 置信度：**中-高**（厂商有官方文档站，但 WebFetch 取到的页面内容被前端 JS 渲染挡住，依赖二手描述；Streamable HTTP 缺位需复测）

---

## 事实 9：Qcoder / Qoder 是什么？是否真实存在？

- **结论：用户文档中提到的 "Qcoder" 几乎可以确定是 "Qoder" 的拼写偏差**。Qoder（谐音 Coder）是阿里巴巴 **2025-08** 推出的独立 AI Agentic 编程 IDE，**真实存在**。
- **官方网站**：https://qoder.com/en （官方一级）
- **MCP 支持**：**是**，**已被列入 modelcontextprotocol.io/clients 官方客户端清单**。
- **官方 MCP 文档**：https://docs.qoder.com/user-guide/chat/model-context-protocol
- **声明的 MCP capabilities**（按官方 clients 列表）：**仅 Tools**
- **平台**：Windows / macOS / Linux 三端全平台桌面客户端
- **配置方式**：设置 → "MCP 服务" → "+ 添加"，打开全局 MCP 配置 JSON；同时提供 "MCP 广场"可视化安装
- **付费**：预览期免费，每月 2000 额度可用 Pro 版功能
- **底层模型**：未公开，由 Qoder 自动路由（推测使用 Qwen3-Coder 系列）
- **与"通义灵码 / Qoder CN"区别**：
  - **Qoder**：阿里巴巴的**独立 IDE**，海外品牌、全平台桌面应用
  - **Qoder CN（原通义灵码 / Lingma）**：阿里云的**插件**，在 JetBrains / VS Code 中工作
  - 二者是同集团不同产品矩阵，但名字撞车容易混淆
- 来源：
  - https://qoder.com/en （Qoder 官方）
  - https://modelcontextprotocol.io/clients （MCP 官方 clients 列表，Qoder 条目）
  - https://docs.qoder.com/user-guide/chat/model-context-protocol （Qoder 官方文档）
  - https://help.aliyun.com/zh/lingma/getting-started/individual-edition-quick-start （阿里云 Qoder CN 文档）
- 置信度：**高**

⚠ 重点核实：**Qcoder 这个写法在搜索引擎和官方网站都找不到对应产品**。若 PRD 之前文档反复出现"Qcoder"，应统一替换为"Qoder"（独立 IDE）或"Qoder CN / 通义灵码"（插件）。

---

## 事实 10：智谱 CodeGeeX 当前 MCP 支持状态

- **是否原生支持 MCP**：**截至 2026-05，未发现智谱官方关于 CodeGeeX 集成 MCP 协议的明确文档或公告**。
- **CodeGeeX 不在 modelcontextprotocol.io/clients 官方客户端清单内**（已对官方 clients 页面全量 grep）。
- **CodeGeeX 当前能力**：基于 GLM-4.5（HBuilderX 插件最新版 1.0.7，2025-11-18 发布），支持代码补全、注释、翻译、Q&A，支持 100+ 编程语言。2025-11 起加入 Claude 4 Sonnet 模型可选。
- **形态**：仅 IDE 插件（VSCode、JetBrains、Vim、HBuilderX、Deepln-IDE 等），**无独立桌面客户端**。
- 来源：
  - https://codegeex.cn/ （官方）
  - https://marketplace.visualstudio.com/items?itemName=aminer.codegeex （VSCode marketplace）
  - https://modelcontextprotocol.io/clients （官方 clients 列表中 grep 无 CodeGeeX）
- 置信度：**中**（官网信息有限；不能 100% 排除某个边缘版本悄悄加了 MCP，但作为"主流支持"来宣称是不成立的）

### 对比：其他社区主流 MCP 客户端
（来自 modelcontextprotocol.io/clients 官方列表，与 CodeGeeX 处于对照位）
- **Cline**：Resources、Tools、Discovery（不支持 Prompts、Elicitation）
- **Continue**：Resources、Prompts、Tools、Apps（不支持 Elicitation）
- **CodeGPT**：仅 Tools（VS Code / JetBrains 插件）

---

## 反复核查事项的结论

### 1. Trae 是否真原生支持 MCP？

**是**。v1.3.0（2025-04-21/22）官方公告明确引入 MCP Server 配置、stdio + SSE 双传输、`.trae/mcp.json` 项目级配置。但 **elicitation 不在 Trae 官方公开声明的能力范围**，且 Trae 未被列入 modelcontextprotocol.io/clients 官方客户端清单，HITL 弹窗能否做出要看实测。**演示视频用 Trae 作为主角是可行的，但若演示包含 elicitation 弹窗，需提前做兼容性回退（例如降级为提示用户在 chat 里手动确认）。**

### 2. CodeBuddy 是真支持 MCP 还是只是 Rules？

**真支持 MCP**。腾讯有完整官方英中文档站（codebuddy.ai/docs/cli/mcp + copilot.tencent.com/docs/cli/mcp），声明 STDIO + SSE + HTTP streaming 三种传输，支持 JSONC、环境变量、三级权限，并已上架 30+ MCP 工具市场。"国产 IDE 全覆盖 MCP"宣传在 CodeBuddy 这一环成立。

### 3. Qcoder 是真实产品吗？

**不是。"Qcoder" 在所有搜索引擎、官方网站均无对应结果，几乎确定是 "Qoder"（阿里巴巴 2025-08 推出的 Agentic IDE）的拼写偏差。** 务必把所有内部文档统一改为 Qoder。Qoder 已被 MCP 官方列入 clients，但**仅声明 Tools**，不要承诺 Resources/Prompts/Elicitation 能用。

### 4. 各客户端 elicitation 实际支持情况

依据 modelcontextprotocol.io/clients **官方一级**统计：

| 客户端 | Elicitation |
|---|---|
| Claude Desktop | ❌ |
| Claude Code | ✅ |
| Claude.ai | ❌ |
| ChatGPT | ❌（仅 Tools/Apps/DCR/CIMD）|
| Cursor | ✅（v1.5+） |
| Codex (OpenAI) | ✅ |
| Continue | ❌ |
| Cline | ❌ |
| GitHub Copilot CLI | ✅ |
| Goose | ✅ |
| Qoder (阿里) | ❌（仅 Tools） |
| Trae / CodeBuddy / Lingma / Comate / CodeGeeX | **均未在官方 clients 列表，elicitation 未声明** |

**对 PRD 撰写的直接影响**：

- 如果 HITL 弹窗依赖 MCP elicitation 协议原语，则**只在 Cursor、Claude Code、Codex、Copilot CLI、Goose 这几个客户端能用**；
- 国产 IDE（Trae、CodeBuddy、Qoder CN、Comate、CodeGeeX）在 elicitation 上**全部需要降级方案**（在 chat 消息里发问 + 用户在 chat 里回答，或外部 URL 跳转）；
- 不能把"全部国产 IDE 都能跑通 HITL 弹窗"作为 demo 承诺，否则会翻车。

---

## 给项目的客观建议

### 可以宣称"100% 跑通（含 elicitation HITL 弹窗）"的客户端
- **Cursor**（v1.5+，2025-08+）
- **Claude Code**（Anthropic CLI）
- **Codex**（OpenAI）
- **GitHub Copilot CLI**

### 可以宣称"100% 跑通（不含 elicitation）"的客户端
- **Claude Desktop**（macOS / Windows，不含 Linux）

### 只能宣称"按版本验证支持 MCP 工具调用"的客户端
- **Trae**：v1.3.0+（2025-04+）
- **CodeBuddy**（腾讯）：IDE 与 CLI 双形态，截至 2025-04 已支持
- **Qoder CN（原通义灵码 / Lingma）**：JetBrains/VS Code 插件 v2.5.0+
- **Qoder**（阿里独立 IDE）：官方仅声明 Tools
- **文心快码 Comate**（百度）：v3.5+（2025-04+）

### 不建议在 PRD 中宣称 "原生 MCP 支持"
- **CodeGeeX**（智谱）：未发现智谱官方关于 MCP 集成的明确文档；可以作为"未来路线"提及，不要写入"已支持"清单。

### 必须修正的项目内部叙述
1. "Trae 100% 支持 MCP" 改为 **"Trae 自 v1.3.0（2025-04）起原生支持 MCP（stdio + SSE），elicitation 待测"**
2. "CodeBuddy 部分支持" 改为 **"CodeBuddy 已完整支持 STDIO + SSE + HTTP Streaming 三种 MCP 传输"**
3. "Qcoder" **全部改为 "Qoder"**（独立 IDE）或 "Qoder CN / 通义灵码"（插件），并明确二者不是同一产品
4. "国产 IDE 全面支持 MCP" 这种绝对化表述要改为 **"国内主流 AI IDE（Trae、CodeBuddy、Qoder CN、文心快码、Qoder）均已支持 MCP 工具调用；HITL elicitation 暂以 Cursor/Claude Code 为参考实现"**
5. 注意"通义灵码"自 2026-05-20 起官方更名为 **Qoder CN**，PRD 时间线之后的部分应改用新名称

---

## 未决问题（pending）

- [ ] **Trae elicitation 实测**：v1.3.0 公告未提及 elicitation，但 2025-06-18 spec 加入 elicitation 后，2025–2026 期间 Trae 是否在某个版本静默加入？需要本地装最新版 Trae 用 MCP Inspector 实测。
- [ ] **CodeBuddy elicitation 实测**：官方文档未声明，需在 CodeBuddy IDE 中以一个会发 elicitation 请求的 MCP Server 测试。
- [ ] **Comate Streamable HTTP**：百度官方截至本次查询只声明 STDIO + SSE，是否已经悄悄加上 Streamable HTTP？需复测最新版。
- [ ] **CodeGeeX 是否在最新插件中加入 MCP**：本次查实 codegeex.cn 官网内容受限，需要直接看 VS Code marketplace 最新 changelog 与 GLM-4.5 / GLM-4.6 发布说明。
