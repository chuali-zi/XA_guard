# Skill 形态产品调研报告

> 任务背景：中国雄安集团比赛 XA-202620，政企智能体安全防护工具。当前方案以 MCP Server 为主形态，本报告评估"Skill + CLI"作为替代/补充形态的产业现状与可行性。
>
> 调研时间窗口：2024 年 10 月 ~ 2026 年 5 月
> 立场：客观调研，不为任何一方背书。

---

## 一、Anthropic Claude Skills：产业现状

### 1.1 时间线与官方定位

Anthropic 于 **2025 年 10 月 16 日** 正式发布 Claude Skills（也称 Agent Skills），随发布提供了 PPTX/XLSX/DOCX/PDF 等内置 Skill，同时在 Claude.ai、Claude Code、API 三端支持自定义 Skill。**2025 年 12 月 18 日**，Anthropic 把 Agent Skills 规范开放为开源标准（agentskills.io），声明 Skill 一处构建可在 OpenAI Codex、Gemini CLI、GitHub Copilot 等平台运行；同时为 Team/Enterprise 客户上线了组织级管理控制台与 Atlassian/Canva/Figma/Notion 等合作伙伴目录 [1][2][3]。

到 **2026 年 2 月-3 月**，Anthropic 进一步推出企业 Agent 计划、Compliance API、Enterprise Analytics API 和带 25 个端点的 Admin API，把 Skill 纳入企业级治理框架 [4][5]。

### 1.2 产品形态：一个文件夹

一个 Skill 在物理上就是一个目录：

```
my-skill/
├── SKILL.md          # 必需。YAML frontmatter（name + description）+ Markdown 指令
├── scripts/          # 可选。可执行脚本（Python / Bash / JS）
├── references/       # 可选。深度参考文档
└── assets/           # 可选。模板、图像、数据文件
```

`SKILL.md` 的 YAML frontmatter 仅包含 `name`（≤64 字符）与 `description`（≤1024 字符）。Markdown 主体即"流程说明书"，告诉 Claude 何时调用、如何分步执行、边界情况怎么处理 [6][7]。

### 1.3 调用机制：渐进披露（Progressive Disclosure）

这是 Skill 形态最关键的设计：

- **启动期**：智能体仅把所有已安装 Skill 的 `name + description` 注入系统提示，每个 Skill 占用 30–100 token。
- **匹配期**：用户提出请求时，Claude 根据 description 判断是否匹配。匹配则调用 `activate_skill` 工具，把 SKILL.md 全文（建议 < 500 行）载入上下文，并把该 Skill 目录加到允许的文件路径中。
- **执行期**：Claude 按指令执行；需要时通过 `run_shell_command` 工具调用 scripts/ 下的脚本（如 `node .gemini/skills/api-auditor/scripts/audit.js`）[8][9]。

调用方式分两种：
- **隐式调用**：模型自动匹配 description 触发；
- **显式调用**：用户输入 `/<skill-name>` 或 `$<skill-name>` 强制激活 [8][10]。

### 1.4 Skill 与 MCP 的官方定位区别

Anthropic 在官方博客（claude.com/blog/skills-explained）和 Help Center 给出了非常明确的对照 [11][12]：

| 对比项 | MCP | Skill |
|---|---|---|
| 解决的问题 | **连接性**（让 Claude 触达外部系统） | **方法论**（让 Claude 知道怎么做） |
| 类比 | "递给 Claude 一把锤子" | "教 Claude 如何用锤子钉钉子" |
| 上下文开销 | 启动即注入所有工具 schema，5 个 MCP server 常占用 ~55,000 token | 启动仅 30–100 token / skill；触发时才载入 |
| 能力边界 | 可访问远程 API、数据库、SaaS | 仅在 Claude 沙箱内运行，无法主动发外部请求 |
| 适用场景 | Claude 需要"够不到"的资源 | Claude 够得到但"做不对" |
| 跨平台 | 已成 Linux Foundation 下 AAIF 标准 | 12 月才开源，跨平台支持刚起步 |

Anthropic 自己测量，开启按需加载后 MCP 的上下文开销可下降 ~85%；Scalekit 的 75 次基准测试显示，回答 "What language is this repo?" 同样问题，MCP 调用比 CLI+Skills 多消耗 **约 32 倍** token；按 Claude Sonnet 4 定价，1 万次调用月成本相差 **17 倍** [13][14]。

Anthropic 反复强调："Skills 和 MCP 不是竞争关系，是同一架构的不同层"——MCP 是水管，Skill 是配方，Plugin 是已经整装好的厨房 [11]。

### 1.5 真实场景案例（公开报道）

- **电商库存**：9 个品牌跨平台库存预测，自动拉 Amazon 数据、按品牌上下文、计算 12 个月销量、给出补货建议 [15]。
- **代码审查**：编码团队 checklist + 静态分析脚本，资深工程师人均节省 20–40 分钟 / PR [15]。
- **合同/法务**：上传合同输出风险清单；NDA 偏差对比；条款检索与改写建议 [15]。
- **Sentry 出品**：`sentry-code-review` skill 自动分析 GitHub PR 中的 bug，通过 Sentry MCP 拉错误数据 [15]——典型 **Skill + MCP 协同**。
- **Snyk、NVIDIA、Trail of Bits** 等都已发布安全主题 Skill 包（含智能合约审计、Semgrep 规则、YARA 规则）[16][17]。
- **金融行业**：Rakuten 报告称使用 Excel 类 Skill 后某财务流程提速约 87.5% [13]。

### 1.6 能力边界

Skill **能做**：
- 在 Claude 沙箱中运行 Python/Bash/JS 脚本
- 读取 Skill 目录内的资源文件
- 通过 Claude 已有的工具（bash、文件读写、MCP 等）间接触达外部

Skill **不能做**：
- 主动发起外部网络请求（必须借 MCP 或 bash + curl）
- 跨 Skill 共享状态（无服务化机制）
- 在用户 IDE 之外作为服务长期运行
- 在没有 Code Execution 沙箱的环境下使用（API 调用必须带 `code-execution-2025-08-25` beta header）[6][7]

---

## 二、OpenAI 阵营：Custom GPTs / Actions

### 2.1 GPTs 的产品形态

OpenAI 的 Custom GPTs 在 ChatGPT 中创建，包含：指令文本（Instructions）、上传的知识文件（Knowledge）、Custom Actions（外部 API 调用能力）和发布到 GPT Store [18]。

### 2.2 Custom Actions：基于 OpenAPI 3.x

Actions 的协议规范严格基于 **OpenAPI 规范**（JSON/YAML），核心字段为 `openapi`/`info`/`servers`/`paths`/`components`。关键约束 [19][20]：
- API 端点 description ≤ 300 字符，参数 description ≤ 700 字符
- OAuth 域名（除 Google/Microsoft/Adobe 外）必须与主端点同域
- 请求/响应载荷 ≤ 100,000 字符
- `x-openai-isConsequential` 字段控制是否每次询问用户：true=必询问；false=允许"始终允许"；未设置时 GET 默认 false，其他默认 true

### 2.3 GPT Store 的"安全/审计/防护"类目

GPT Store 没有独立的"Security"主类，但在 Productivity 与 Programming 类目下有大量自定义 GPT 提供 prompt-injection 检测、合规问答、CVE 查询等服务。OpenAI 自己提供的 SOC2 Type 2、ISO 27001/27017/27018/27701、PCI-DSS 认证主要面向 ChatGPT 与 API 服务，**对第三方 GPT 不做独立验证**——Dark Reading 与 Reco.ai 等机构均指出，GPT Store 因 UI 与官方 GPT 一致存在欺骗性、且 API 提供方的隐私实践 OpenAI 不背书 [21][22][23]。第三方监控产品（Reco、Opsin、Microsoft Purview）已经在做 GPT 行为审计与 prompt 拦截。

### 2.4 形态对比

| 维度 | Custom GPT + Actions | Claude Skill |
|---|---|---|
| 协议 | OpenAPI 规范（强 schema） | Markdown + YAML（弱 schema） |
| 调用方 | ChatGPT 用户对话触发 | 任意支持 Agent Skills 的智能体 |
| 分发渠道 | GPT Store（封闭，OpenAI 审核） | GitHub / agentskills.io / 各平台目录（开放） |
| 是否可执行本地代码 | 否（只能调远程 API） | 是（可带 scripts/） |
| 用户调用方式 | 启动该 GPT 后所有对话默认在其上下文 | 渐进披露，按需激活 |

可以看出：**GPT 是"垂直应用形态"，Skill 是"能力插件形态"**。前者把用户拉进一个固定语境，后者让通用智能体在需要时加挂能力。

---

## 三、IDE 类 AI 工具的 Rules / Custom Instructions

### 3.1 Cline / Cursor 的规则文件

- **Cursor**：早期用 `.cursorrules`（项目根目录单文件），现已弃用，改为 `.cursor/rules/*.mdc`（Markdown + YAML frontmatter，可按文件类型/框架/工作流分文件加载）[24]。
- **Cline**：早期用 `.clinerules` 单文件，现改为 `.clinerules/` 目录可包含多文件；支持 toggleable rules、Plan/Act 双模式 [25][26]。
- 还有 `.windsurfrules`（Windsurf）、`AGENTS.md`（OpenAI Codex）、`.github/copilot-instructions.md`（GitHub Copilot）等等价物。

### 3.2 国产 IDE 的等价机制

- **腾讯 CodeBuddy**：官方文档 codebuddy.cn/docs/ide/User-guide/Rules 明确提供"多层级 Rules 系统"——可在不同作用域定义 AI Agent 行为，把 prompt、workflow、编码规范打包用于团队管理与最佳实践共享 [27]。
- **阿里通义灵码**：2025 年 5 月发布 AI IDE，Agent 能力大幅增强，但其规则机制更偏 Project-level System Prompt + 工具调用，不像 SKILL.md 那样有独立的发现/激活生命周期 [28]。
- **字节 Trae**：2.0 进入 SOLO 模式，强调全流程自动化；中文指令理解准确率比 Cursor 高 ~18%（4 月评测）；规则机制以 `AGENTS.md`/`.trae/rules` 形态存在 [29][30]。

### 3.3 这种"规则文件"算不算 Skill 形态？

**部分算，部分不算**。Anthropic 在 skills-explained 博客里专门做了区分 [11]：
- **Cursor/Cline rules** ≈ 始终加载的 Project Knowledge，等价于 Claude 的 Projects 或长期记忆，**不是** Skill；
- **Skill** 的关键差异是 **按需激活**（progressive disclosure）+ **可携带可执行脚本** + **可跨 session 复用**。

GitHub 仓库如 `solutionforest/neo-skill` 已经开始做"一次写、多端格式适配"——同一份核心指令同时输出为 `SKILL.md` / `.cursorrules` / `AGENTS.md` 等格式 [31]。说明业界正在把 Skill 视为这一类规则机制的**最通用超集**。

---

## 四、学术界研究

### 4.1 Skill 抽象的形式化

**SoK: Agentic Skills — Beyond Tool Use in LLM Agents**（arXiv:2602.20867）是目前最重要的奠基论文。它给出严格定义 [32]：

> Skill 是一个可重用、可调用的模块，封装一组动作或策略序列，使智能体能在重复出现的条件下达成一类目标。Skill 与 tool（原子原语、固定接口）、plan（一次性推理脚手架）、episodic memory（存储观察）三者并列，特点是**同时可执行、可复用、可治理**。

论文提出 **四级执行框架** —— 与本任务高度相关：
- Tier-1：仅文档（不进入上下文）
- Tier-2：指令访问（instruction access）—— Skill 的 NL 指令进入上下文，但若不强制 read-only 模式，会"退化"为 Tier-3
- Tier-3：监督执行（每个动作需用户批准或沙箱）
- Tier-4：自主执行（按预配权限边界运行）

### 4.2 用户主动调用 vs 透明自动应用

学术界目前没有专门论文做"Skill（用户主动调用）vs MCP（透明代理）"的安全保证对照。但相关讨论分散在几篇文献中：

1. **Schmotz et al., "Agent Skills Enable a New Class of Realistic and Trivially Simple Prompt Injections"**（arXiv:2510.26328，ELLIS Institute Tübingen，2025/10）：直接攻击 Anthropic Skills，证明在长 SKILL.md 与脚本中藏匿恶意指令可触发数据外泄；并演示"Don't ask again"批准如何被滥用 [33]。
2. **"When Skills Lie: Hidden-Comment Injection in LLM Agents"**（arXiv:2602.10498）：标准 prompt injection 在 Skill 中容易被用户发现，但攻击者可隐蔽化注入 [34]。
3. **"Skill-Inject: Measuring Agent Vulnerability to Skill File Attacks"**（arXiv:2602.20156）：系统性度量 Skill 文件攻击成功率 [35]。
4. **"Governance Architecture for Autonomous Agent Systems"**（arXiv:2603.07191）：把恶意 Skill 插件与 RAG 投毒并列为主要威胁，引用 InjecAgent 在 ReAct 风格智能体上的 60%+ 攻击成功率 [36]。
5. **Meta AI "Agents Rule of Two"**（2025/10）：在 prompt injection 仍无法可靠检测前，agent 一次 session 内三个能力（处理不受信内容、访问敏感资源、外部通信）至多取其二 [37]。

学界共识：**Skill 形态的"主动调用"本身并不提供更强的安全保证**——只要 Skill 内容进入上下文且伴随脚本执行，攻击面与 MCP 相当甚至更大（因为 SKILL.md 比 MCP schema 更易写成自然语言长文本）。

### 4.3 用户体验维度

学术界对"显式主动调用 vs 透明代理"的 UX 差异有零散研究：
- 显式调用（`/xa-guard ...`）让用户保持 control，便于责任归属；
- 透明应用减少操作摩擦，但削弱 trace ability。

Skill 的设计折中：**默认隐式触发，必要时显式 `/skill-name` 强制**。

---

## 五、做"安全 Skill"会怎样

### 5.1 假想场景：`xa-guard` Skill

用户在 Claude Code / Codex / 任意支持 Agent Skills 的智能体里说：

> "用 xa-guard 检查这次调用，然后把审计 JSON 写到 .xa/audit.json"

产品形态会是：

```
xa-guard/
├── SKILL.md                          # YAML: name=xa-guard, description="政企智能体调用合规审计"
├── scripts/
│   ├── inspect.py                    # 解析最近一次 tool call
│   ├── policy_check.py               # 策略命中检测
│   └── redact.py                     # 敏感字段脱敏
├── references/
│   ├── policies/                     # 各类政企合规规则（信创、等保、密码法）
│   └── threat-model.md
└── assets/
    └── report.template.md
```

SKILL.md 的 description 写成：
> "当用户希望审计或检查智能体本轮工具调用的合规性、敏感字段泄露、跨域调用、未授权权限时使用。触发词：审计、合规、信创、脱敏、xa-guard。"

### 5.2 Skill + CLI 联动模式

这是当前业界最现实的工程模式（参考 Atlassian TWG CLI、Anthropic 自己的官方 Skills、Snyk 的安全 Skills）[38][39]：

1. 用户/智能体显式或隐式触发 Skill。
2. SKILL.md 指示智能体**调本地 `xa-guard` CLI**（通过已有 bash 工具）：
   ```bash
   xa-guard scan --transcript last --policy ./policies/govcloud.yaml
   ```
3. CLI 执行确定性、可审计、可单独发版的安全逻辑（核心检测算法、规则引擎、密码合规检查）。
4. CLI 输出 JSON 到固定路径。
5. SKILL.md 指示智能体读 JSON、按 `report.template.md` 渲染人类可读报告。

**好处**：
- Skill 仅负责"调度 + 渲染"，CLI 承担实际安全逻辑——确定性高、可被传统工具链审计、可独立版本管理（参考 `gh skill`、`uvx`）。
- CLI 本体可单独打包成 PyPI/Cargo/Go binary，不依赖任何 AI 平台。
- Skill 文件可发布到 SkillsMP / agentskills.io / 内部 Marketplace，跨 Claude/Codex/Gemini/Copilot 运行。

### 5.3 工程投入估算（粗）

| 模块 | 工作量（人天） | 备注 |
|---|---|---|
| `xa-guard` CLI 核心（策略引擎 + 规则定义 + JSON 报告） | 8–12 | 主体是规则与解析，AI 无关 |
| SKILL.md 与 scripts/ 适配（含中英文 description）| 1–2 | 主要是写文档与模板 |
| 多端测试（Claude Code、Codex CLI、Gemini CLI）| 2 | 路径与权限差异 |
| Skill 安全自审计（避免本身被攻击）| 2 | 参考 Snyk threat model 与 Repello AI 审计清单 |
| 文档与 Demo 视频 | 2 | 比赛与答辩需要 |
| **合计** | **15–20 人天** | 单人 3 周可达可演示状态 |

对比同等功能的 **MCP Server**：MCP 需要长期运行进程、HTTP/stdio 协议、tool schema、生命周期管理、远程鉴权——同等功能投入约 20–30 人天。

---

## 六、客观结论：Skill 形态值不值得选

### 6.1 Skill 形态的真实优势

1. **上下文成本极低**。MCP 5 server 启动占 ~55k token，等效 Skill 集合占 ~500 token；按真实基准 1 万次月调用，token 成本相差 17 倍 [13]。
2. **分发与跨平台**。规范已开源，同一份 Skill 可在 Claude、Codex、Gemini CLI、GitHub Copilot、Cursor、Kiro、Atlassian TWG 等运行；MCP 虽然也是标准，但 server 必须分别部署与适配，Skill 是"文件即产品"[3][8][9][38]。
3. **作者门槛低**。Markdown + YAML，团队任何成员都能写。MCP 需要懂协议、写服务、做鉴权。
4. **可审计性强**。Skill 是版本化文本，可 git 跟踪、可 PR review，比"运行中的 MCP server"更容易做合规审查与变更追溯 [40]。
5. **与本地 CLI 天然契合**。Skill 调本地 bash 是官方鼓励的模式，对中国信创/私有化场景非常友好——CLI 本体可不出域，不依赖任何远程服务。

### 6.2 Skill 形态的真实劣势（必须正视）

1. **运行依赖严格**。需要目标智能体支持 Agent Skills 规范且开启 Code Execution（沙箱）。Claude Pro+ / Codex CLI / Gemini CLI 都已支持，但**国产 Trae / 通义灵码 / 文心快码尚未原生支持 SKILL.md 规范**（截至 2026 年 5 月）。如果你们的目标用户是国产 IDE 用户，Skill 形态的覆盖率不如 MCP。
2. **安全风险大、且学术界已经证明**。arXiv 2510.26328 直接演示 SKILL.md 是天然的 prompt injection 载体；arXiv 2602.20867 描述了 ClawHavoc 事件（1200 个恶意 Skill 渗入 marketplace）。**做"安全工具"用一个"已知存在安全短板"的载体，需要把自身 Skill 的防御做到极致**——这反而是个加分项，因为你们的产品定位就是解这个问题。
3. **没有持久态、没有服务**。Skill 是"一次性脚本调用"模型，不能跑长时任务、不能维护连接池、不能做事件推送。如果产品方案需要"持续监控""异步审计""跨 session 状态"，Skill 不胜任，必须靠 CLI 进程或 MCP server。
4. **国产平台支持不确定**。CodeBuddy 有自己的 Rules 系统但格式不同；通义灵码、Trae 是否会跟进 Agent Skills 开放标准，目前**没有公开承诺**。这是雄安比赛这种"政企场景"的关键风险——评委可能更看重"在国产平台跑得起来"。
5. **生态成熟度比 MCP 弱**。MCP 已有 10,000+ server，进入 Linux Foundation 治理；Skill 标准 2025/12 才开放，生态在快速增长但还远不及。

### 6.3 与 MCP 的逐维对照

| 维度 | MCP 形态（当前方案） | Skill+CLI 形态（拟评估） | 胜出 |
|---|---|---|---|
| 上下文开销 | 高（数万 token） | 极低 | **Skill** |
| 跨平台分发 | 需逐平台部署 server | 文件即可分发 | **Skill** |
| 国产 IDE 覆盖 | MCP 已被部分国产工具接入（CodeBuddy 等） | 国产支持尚不明朗 | **MCP** |
| 持久服务能力 | 强（长进程、事件推送） | 弱（每次调用） | **MCP** |
| 安全审计成熟度 | 协议层有鉴权、传输安全 | Skill 文本攻击面被学术证明 | **MCP** |
| 政企私有化适配 | 需要部署 server | CLI 本地化更简单 | **Skill** |
| 工程投入（同功能） | 20–30 人天 | 15–20 人天 | **Skill** |
| 评委技术认知熟悉度 | 较高（已成热门话题 1.5 年） | 较低（2025 年 10 月才发布） | **MCP** |
| 创新性叙事 | 中等 | 高（"新形态 + 雄安场景"） | **Skill** |

### 6.4 给比赛团队的明确建议

**结论：建议把 Skill 形态作为"补充形态"或"演示形态"，而不是主形态替换 MCP。**

理由：
1. **比赛评委维度**：雄安政企比赛大概率更看重"能落地、能在国产环境跑、有完整审计链路"。MCP 在这些维度已经被验证，Skill 在国产平台的支持还是个变量。
2. **技术风险**：把核心安全防护能力（你们的差异化所在）押在 Skill 上，意味着你们要同时解决"Skill 形态本身的安全问题"和"你们要防护的智能体安全问题"——双战场不利。
3. **更优组合**：
   - **主形态保持 MCP Server**：负责持久监控、跨 session 审计、与其他工具链对接，这是政企场景的核心；
   - **同时发布 `xa-guard` CLI**：作为独立可执行体，可在没有 AI 的环境单独跑，符合信创/私有化要求；
   - **附加 `xa-guard` Skill 包**：作为"开发者快速接入"的轻量入口，调本地 CLI，提升 demo 与生态故事性；
   - **三者共用同一份策略规则与检测算法**（核心算法在 CLI，MCP 与 Skill 都是 adapter）。
4. **叙事价值**：在答辩或路演时，可以宣称"我们同时提供 MCP / CLI / Skill 三种形态，覆盖政企现有 AI 工具链的所有主流接入方式"。这比单一形态更有说服力。

**不推荐方向**：单独把 Skill 形态作为唯一/主形态。如果国产平台跟进慢、或者评委不熟悉这个新概念，你们会失去主要技术展示点。

---

## 七、参考来源

[1] Anthropic, "Introducing Agent Skills", https://www.anthropic.com/news/skills
[2] Verdent Guides, "Claude Skills: Launch Timeline & Technical Overview", https://www.verdent.ai/guides/claude-skills-announcement-news
[3] SiliconANGLE, "Anthropic makes agent Skills an open standard", https://siliconangle.com/2025/12/18/anthropic-makes-agent-skills-open-standard/
[4] VentureBeat, "Anthropic launches enterprise 'Agent Skills' and opens the standard", https://venturebeat.com/ai/anthropic-launches-enterprise-agent-skills-and-opens-the-standard
[5] TechCrunch, "Anthropic launches new push for enterprise agents", https://techcrunch.com/2026/02/24/anthropic-launches-new-push-for-enterprise-agents-with-plugins-for-finance-engineering-and-design/
[6] Anthropic Engineering, "Equipping agents for the real world with Agent Skills", https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills
[7] Anthropic, "Agent Skills" API Docs, https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview
[8] OpenAI Developers, "Agent Skills – Codex", https://developers.openai.com/codex/skills
[9] Gemini CLI, "Agent Skills", https://geminicli.com/docs/cli/skills/
[10] Kiro, "Agent Skills CLI Docs", https://kiro.dev/docs/cli/skills/
[11] Anthropic, "Skills explained: How Skills compares to prompts, Projects, MCP, and subagents", https://claude.com/blog/skills-explained
[12] Anthropic Help Center, "What are Skills?", https://support.claude.com/en/articles/12512176-what-are-skills
[13] DEV Community / Jim Quote, "Claude Skills vs MCP: Complete Guide to Token-Efficient AI Agent Architecture", https://dev.to/jimquote/claude-skills-vs-mcp-complete-guide-to-token-efficient-ai-agent-architecture-4mkf
[14] IntuitionLabs, "Claude Skills vs. MCP: A Technical Comparison", https://intuitionlabs.ai/articles/claude-skills-vs-mcp
[15] aiblewmymind.substack.com, "39 Claude Skills Examples to Transform How You Work", https://aiblewmymind.substack.com/p/claude-skills-36-examples
[16] Snyk, "Top 9 Claude Skills for Cybersecurity", https://snyk.io/articles/top-claude-skills-cybersecurity-hacking-vulnerability-scanning/
[17] NVIDIA Developer, "NVIDIA-Verified Agent Skills Provide Capability Governance for AI Agents", https://developer.nvidia.com/blog/nvidia-verified-agent-skills-provide-capability-governance-for-ai-agents/
[18] OpenAI Help Center, "Configuring actions in GPTs", https://help.openai.com/en/articles/9442513-configuring-actions-in-gpts
[19] OpenAI Developers, "GPT Actions", https://developers.openai.com/api/docs/actions/introduction
[20] OpenAI Platform, "Production notes on GPT Actions", https://platform.openai.com/docs/actions/production
[21] Dark Reading, "OpenAI's New GPT Store May Carry Data Security Risks", https://www.darkreading.com/cyber-risk/openai-new-gpt-store-data-security-risks
[22] Reco.ai, "Custom GPT Security Best Practices", https://www.reco.ai/learn/custom-gpt-security
[23] OpenAI Trust Portal, https://trust.openai.com/
[24] Cursor (PatrickJS/awesome-cursorrules), https://github.com/PatrickJS/awesome-cursorrules
[25] DataCamp, "Cline AI: A Guide With Nine Practical Examples", https://www.datacamp.com/tutorial/cline-ai
[26] Tembo, "Cursor vs Cline", https://www.tembo.io/blog/cursor-vs-cline
[27] 腾讯云 CodeBuddy 官方文档, "规则", https://www.codebuddy.cn/docs/ide/User-guide/Rules
[28] 知乎, "通义灵码 - 阿里云推出的AI编程助手", https://zhuanlan.zhihu.com/p/1988722703675462734
[29] CSDN 博客, "国内AI IDE竞逐：腾讯CodeBuddy、阿里通义灵码、字节跳动TRAE、百度文心快码", https://blog.csdn.net/qq_44866828/article/details/149658023
[30] zeeklog, "字节 Trae vs 腾讯 CodeBuddy vs 阿里 Qoder", https://www.zeeklog.com/zi-jie-trae-vs-teng-xun-codebuddy-vs-a-li-qoder-san-da-ai-ide-ji-cheng-onecode-shen-du-dui-bi-yu-ti-yan-ce-ping/
[31] GitHub solutionforest/neo-skill, https://github.com/solutionforest/neo-skill
[32] arXiv:2602.20867, "SoK: Agentic Skills — Beyond Tool Use in LLM Agents", https://arxiv.org/pdf/2602.20867
[33] arXiv:2510.26328, "Agent Skills Enable a New Class of Realistic and Trivially Simple Prompt Injections", https://arxiv.org/abs/2510.26328
[34] arXiv:2602.10498, "When Skills Lie: Hidden-Comment Injection in LLM Agents", https://arxiv.org/pdf/2602.10498
[35] arXiv:2602.20156, "Skill-Inject: Measuring Agent Vulnerability to Skill File Attacks", https://arxiv.org/pdf/2602.20156
[36] arXiv:2603.07191, "Governance Architecture for Autonomous Agent Systems", https://arxiv.org/pdf/2603.07191
[37] Simon Willison, "New prompt injection papers: Agents Rule of Two", https://simonw.substack.com/p/new-prompt-injection-papers-agents
[38] Atlassian Developer, "TWG CLI Agent Skills", https://developer.atlassian.com/cloud/twg-cli/agents/skills/
[39] GitHub Changelog, "Manage agent skills with GitHub CLI", https://github.blog/changelog/2026-04-16-manage-agent-skills-with-github-cli/
[40] Microsoft Learn, "Agent Skills", https://learn.microsoft.com/en-us/agent-framework/agents/skills
[41] InfoQ, "Anthropic Introduces Skills for Custom Claude Tasks", https://www.infoq.com/news/2025/10/anthropic-claude-skills/
[42] Simon Willison, "Claude Skills are awesome, maybe a bigger deal than MCP", https://simonwillison.net/2025/Oct/16/claude-skills/
[43] GitHub anthropics/skills, https://github.com/anthropics/skills
[44] The New Stack, "Agent Skills: Anthropic's Next Bid to Define AI Standards", https://thenewstack.io/agent-skills-anthropics-next-bid-to-define-ai-standards/
