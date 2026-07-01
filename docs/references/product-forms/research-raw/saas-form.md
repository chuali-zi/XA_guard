# 外置 SaaS / HTTP API 形态可行性调研报告

> ⚠ **本调研报告已被 [`docs/source-of-truth/事实源.md`](../../../source-of-truth/事实源.md) v1.1（2026-05-24）更新**。
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

> 调研对象：XA-202620 政企智能体安全防护赛题的"产品形态"二次评估
> 当前主推：MCP Server（XA-Guard 三件套形态之一）
> 备选方案：外置 SaaS / HTTP API 服务（agent 通过 HTTPS 调用我方 endpoint）
> 时间：2026-05-23
> 调研方法：WebSearch + WebFetch，覆盖国际 Top5 + 国产 Top5 商业产品，叠加政企合规与学生团队可行性视角
> 结论性质：客观研究，**不为支持新方案而美化**

---

## 0. 一句话先抛结论

**外置 SaaS / HTTP API 形态在政企智能体安全防护场景下是"国际主流默认形态、国内可行但不该作为主推、学生团队尤其不该自建"的产品形态。** 我们的赛题语境下，**应该坚持 MCP Server 主推**，但可以把"SDK / HTTP Inspection API"作为三件套里的一个补充形态保留（与目前规划一致），不必走"全力 SaaS 化"路线。

详细推导见后文。

---

## 1. 国际主流商业产品形态地图

### 1.1 Lakera Guard（瑞士苏黎世，2024 明星初创，2025-Q4 被 Check Point 收购）

**形态**：HTTP API 为核心，单一 POST 调用接入。

- 公开 SaaS：`POST https://api.lakera.ai/v2/guard`，请求体为 OpenAI chat completions 兼容格式，30 分钟可完成集成 [1]。
- 自托管容器（Docker）：企业版客户可拿到容器镜像，部署在自己 VPC 内，**自托管版本不需要 API Key**（按容器健康检查端点鉴权）[1]。
- 多区域：US / EU / AU 等区域可选，企业级支持 SOC2 / GDPR / NIST 合规 [2]。
- 性能：sub-50ms 延迟，FPR < 0.5%，宣称 98%+ 检出率 [3]。

**客户案例**：
- **Dropbox** 是公开标杆，关键引用："他们之所以选 Lakera，是因为可以把 Lakera Guard 跑在自己的 Docker 容器里作为内部微服务" [4]。**这是高质量证据：Fortune 500 客户在采购"SaaS 公司"的产品时，仍然要求'自托管'形态** —— 说明纯 SaaS 在企业级是难以单独成立的。
- 截至 2025-10，覆盖 200+ 企业 AI 应用，月处理 10M+ 交互 [3]。
- 行业：金融、医疗、科技、教育，未见明确政府/国防客户公开案例。

**定价**：Community 免费版（1 万次/月）+ Enterprise 定制价（未公开）；Enterprise 才解锁自托管、SSO、SIEM 集成、数据驻留选项 [2]。

**收购信号**：2025-05 传 Cisco 收购、最终 2025-Q4 由 Check Point 完成收购 [5]。**即"独立 SaaS 公司"在 AI 安全赛道难以独立长期存活，大都被传统安全巨头吸收**。

### 1.2 CalypsoAI（美国，国防/政府焦点，2025-09 被 F5 以 $1.8 亿收购）

**形态**：完整平台 + 部署灵活性（SaaS / 本地 / VPC）。

- 主打能力：**Inference Red-Team + Agentic Warfare**（红队评测）/ Security Leaderboard（模型安全排行榜）/ 实时 inference 层防御 [6]。
- 强调："基础设施团队希望对'AI 安全工具放在哪里'有自主权" → **明确提供 on-prem 选项给敏感数据客户** [6]。

**政府/国防客户**：
- Lockheed Martin Ventures 自 2020 年起多轮领投，并把 CalypsoAI 与 Fiddler 并列定位为"满足 DoD 'Traceable / Reliable AI' 原则"的供应链伙伴 [7]。
- 与 Palantir 联手"为美国政府提升 AI 安全" [6]。
- 客户名单含 Palantir、SGK，被选为 DoD AI Readiness Services 合作伙伴 [6]。
- Lockheed 自己采用了一个对照样本：内部用 LMText Navigator（基于 Llama），**完全本地化部署，4 万员工使用，敏感数据不出内网** [7]。

**重要观察**：CalypsoAI 自身定位"安全 SaaS"，但其**真正的政府客户都是要求本地化交付的**。这与 Lakera-Dropbox 模式完全一致。

### 1.3 Robust Intelligence → Cisco AI Defense（2024-10 收购）

**收购前**：业内"AI Firewall"概念创始者，2024 Gartner Cool Vendor [8]。

**收购后形态**（Cisco AI Defense 2025）：**多形态并行**：
1. **Inline Gateway（代理）**：把 AI 应用的 model URL 替换成 gateway URL，全部流量走代理。
2. **Inspection API**：开发者主动调用 API endpoint，自己决定阻断逻辑（这就是"外置 SaaS API"形态）。
3. **云原生集成**：直接和 Google Cloud Agent Gateway、GKE Service Extensions、Gemini Enterprise Agent Platform 集成。
4. **On-prem AI POD**：在客户 OCP 集群里部署 Ingress + Proxy Gateway + API endpoint，**承诺所有推理流量、MCP 交互、agent workflow、运行时策略只在客户环境内执行，只把 management plane 元数据回传 Cisco** [9]。

**特别值得我们关注**：Cisco 在 2026-02 把 AI Defense 扩展到 agentic era，**新增 AI BOM、MCP Catalog、algorithmic red teaming、real-time agentic guardrails** [9]。说明**头部商业产品也在拥抱 MCP，并不与之对立**。Cisco 开源仓 `cisco-ai-defense/defenseclaw` 就是"Security Governance for Agentic AI"。

### 1.4 Protect AI（2025 被 Palo Alto 收购）

**形态**：商业平台 + 开源工具混合。
- **商业**：Guardian + Recon + Layer 三合一统一平台，Layer 是 runtime D&R（30+ 策略，挡 Unicode 操纵、PII 泄露、jailbreak）[10]。
- **开源**：LLM Guard（Python 包，"工具箱"形态）+ ModelScan（模型扫描器）。
- **集成方式**：合作伙伴渠道 + Hugging Face / Microsoft / Databricks 技术联盟。

**形态选择观察**：**Protect AI 是少数把"开源 SDK + 商业 SaaS"两条腿走路的厂商**。这对我们的赛题很有启发——这两种形态可以并存。

### 1.5 HiddenLayer（AISec Platform 2.0，2025-04 发布）

**形态**：**Model-agnostic + Agentless** —— 强调"不需要访问模型权重、训练数据、prompt"。
- 模型扫描（35+ 格式：PyTorch / TF / ONNX / GGUF / pickle / safetensors）通过 Web UI 或 API 上传 [11]。
- AI Detection & Response（AIDR）：**只观察模型的"向量化输入"**，不接触数据，定位是"非侵入式" [12]。
- AI BOM + Model Genealogy（2025 新功能）：模型族谱+物料清单。

**核心创新点**：把"不接触客户数据/不接触模型权重"作为卖点 —— 这正是企业客户对外置服务的最大顾虑的反向应对。

---

## 2. 国产同类商业产品形态地图

### 2.1 百度智能云 - 千帆 4.0 安全 + 大模型内容安全平台

**形态**：**公有云 API + 私有化 + 混合云专线** 全形态可选。

千帆 4.0（2025-09 发布安全白皮书）：
- 公有云：API 接入，按 token / 调用计费。
- **混合云专线/VPC 内网调用**：解决"私域数据不碰公网"诉求（中大企业核心需求）[13]。
- **六大维度防护**：平台-模型-数据-内容-运营-合规。
- 应用行业：金融、政务、医疗。

**内容安全平台**：开箱即用的"大模型安全护栏产品矩阵"。

### 2.2 阿里云 - AI 安全护栏（云盾系列）

**形态**：API 调用 + Bailian 平台一键开通，**也支持私有化**。

- 5 大能力：内容合规 / 敏感数据 / 提示注入 / 恶意文件/URL / 数字水印 [14]。
- 内容审核大模型 2.0（融合 Qwen3Guard，多模态）；数据安全识别 800+ 类型（融合 Qwen-Plus，精度+35%）。
- 计费：**调用次数 + Token 双轨**，配置灵活。
- 性能：**毫秒级 + 千级并发**。

**重点**：阿里云明确把"AI Agent"作为护栏的目标用户之一，已经在做"agent 调护栏"模式 —— **这正是我们设想的"agent 通过 HTTP 调用安全服务"的国产范本**。

### 2.3 腾讯云 - 天御 + LLM-WAF + AI-SPM

**形态**：**多产品矩阵 + 公有云 / 混合云 / 私有化全覆盖**。

三大主力产品（2025-09 数生大会发布）[15]：
- **LLM-WAF 大模型防火墙**：**5 分钟接入**（注意这个数字），兼容混元、DeepSeek 等。
- **AI-SPM 大模型态势管理**：AI-BOM + 攻击面 + 漏洞管理。
- **天御大模型安全网关**：以"统一企业智能体应用和 MCP 服务身份和权限管控"为核心 —— **腾讯已经直接提到 MCP**，是国产厂商里最早做 MCP 安全网关的。

腾讯框架："7 个层级、26 个控制模块、130+ 项控制措施"。

### 2.4 智谱 AI - GLM 安全 + 私有化方案

**形态**：**公有 MaaS API + 云上私有实例 + 完全本地化部署** 三档可选。

- 商业模式："销售 Token 流"为主 [16]。
- **但**：政企客户（央国企）几乎全走私有化。一个公开数据点：智谱 2024 在地方政府的私有化部署可做到"零数据出境，业务咨询准确率 92%" [16]。
- 截至 2025-09，1.2 万企业客户。

### 2.5 360 安全大模型 + 大模型安全卫士

**形态**：**公有云 + 私有化双轨**，私有化为政企主要交付方式。

- 私有化形态：**"安全大脑 + 安全大模型 + 探针"三位一体** [17]。
- 客户：网信、政府、央企、运营商。
- 2025 在乌镇峰会发布《大模型安全白皮书》，提出"风险盘点 → 外挂部署 → 原生构建"三步走 —— **"外挂部署"恰好是我们要评估的 SaaS / 外置形态**。
- IDC 2024 安全大模型实测综合第一 [18]。

### 2.6 国产产品共同特征总结

| 厂商 | 公有云 API | 私有化 | 混合云 | MCP 关注 |
|------|------------|--------|--------|----------|
| 百度千帆 | 有 | 有 | 有（专线） | 间接 |
| 阿里云盾 | 有 | 有 | 有 | 间接 |
| 腾讯天御 | 有 | 有 | 有 | **明确（安全网关核心）** |
| 智谱 | 有 | 有（主力） | 有 | 暂未公开 |
| 360 | 有 | **主力** | 有 | 暂未公开 |

**结论**：**国产没有任何一家敢做"只 SaaS、不私有化"的产品** —— 政企买大模型安全的天花板就是"必须支持私有化"。

---

## 3. 政企客户对"外置服务"形态的真实接受度

### 3.1 现实数据：私有化是主流

- 思瀚产研：**接近 60% 企业** 把 AI 推理模型放在本地数据中心 / 私有云 / 边缘 [19]。
- 大模型内容安全细分赛道：年规模约 5 亿元，**TOP3 厂商占 2.5 亿，其中私有化占总盘 1/10（约 5000 万）** —— 私有化项目数少但单价高 [20]。
- 政府机构 + 央国企："私有化部署的主力军"，原因有二：
  1. "重硬轻软"投资惯性、国资保值增值的硬件采购导向。
  2. 数据安全顾虑 + RAG 引入大量内部专有知识 → 不允许出网。

### 3.2 等保 2.0 与数据出境视角

- 等保 2.0 视角下：**SaaS 模式云厂商承担 90%+ 安全责任** —— 听起来对甲方有利，但反过来意味着甲方对数据流转失去控制 [21]。
- 数据出境判定：**"出境"以物理存储位置为准** —— 即使是境内云区域，只要走"非自管 SaaS"，就有合规审查路径。**如果训练数据/交互数据 > 1 万条个人信息要跨境，必须过安全评估** [22]。
- GB/T 45654-2025（生成式 AI 安全基本要求）：明确把数据分级（公开/内部/机密/绝密）作为强制要求，**绝密数据建议"私有化 + 加密"**。
- 上海消防救援局解释为何选本地化部署 DeepSeek 的官方原话：**"实现数据传输处理过程中的网络和数据安全"** —— 政企典型话术。

### 3.3 SaaS 模式的现实墙

- 政企报告（中国电信 + 信通院 + 百度 + 火山引擎 + 360 + 软通 联合）总结的政企 AI Agent **三条路径**：① SaaS 账号式服务 / ② API 嵌入式服务 / ③ 定制化服务 —— **政务、央国企、金融大客户公认走第三条（定制化 + 私有化）** [23]。
- "中国 SaaS 一直缺乏实力雄厚的公司" —— 行业普遍认知 [19]。

### 3.4 但 SaaS 也不是完全没空间

- 中小企业 / 合规压力中等的场景 / 快速 POC 验证：**SaaS 反而是优选**（开箱即用、订阅制、合规复用云厂商资质）。
- "公共云优先"理念已被政府推动，未来 5 年可能松动 —— 但赛事节点（2026-09）窗口期内不会有质变。

---

## 4. 关键产品形态对比（MCP Server vs HTTP API SaaS vs SDK）

### 4.1 三种形态在赛题语境下的对比

| 维度 | MCP Server（当前主推） | 外置 HTTP API / SaaS | SDK / Library |
|------|------------------------|---------------------|---------------|
| **学生工程量** | 中（MCP 协议已标准化，照官方 SDK 写） | **高**（需自管 endpoint、监控、防 DDoS、HTTPS 证书、计费、SLA） | 低 |
| **政企接受度** | 中（新但增长极快） | **低**（"外置服务"=数据出网恐惧） | 高（pip install 就能跑） |
| **创新性叙事** | **强**（蹭 MCP 生态 + 协议中立卖点） | 中（与 Lakera/Cisco AI Defense 同质化） | 弱（与 LLM Guard / Llama Guard 同质化） |
| **演示效果** | **强**（Trae/Cursor 改一行 mcp.json 就生效，直观） | 中（要写一段调用代码） | 中 |
| **产品锚点** | **明确**（"防护栏"具象） | 抽象（"我们的服务"） | 抽象（"我们的包"） |
| **基础设施成本** | 0（用户自部署） | **高**（要 24x7 跑）| 0 |
| **可被引用的论文/工程范本** | Anthropic MCP 官方 + 腾讯天御安全网关 | Lakera / Cisco AI Defense Inspection API | LLM Guard / NeMo Guardrails |
| **30 页方案"完整性"分数** | 高（Server + Protocol + SDK 三件套已覆盖三种形态） | 中 | 中 |
| **客户改造成本** | 低（改 mcp.json） | 中（改代码 + 加 HTTP 客户端） | 高（要 import + 学 API） |

### 4.2 关键发现：商业产品都在"多形态并行"

- Cisco AI Defense：Gateway + Inspection API + Cloud-native Hook + On-prem POD（4 形态）。
- Lakera：SaaS API + Self-hosted Container（2 形态）。
- 阿里云盾：API + 平台一键开通 + 私有化（3 形态）。
- 腾讯：LLM-WAF（接入） + AI-SPM（治理） + 天御网关（MCP 身份）（3 产品 × 多形态）。

**没有任何一家头部产品只做单一形态**。这给我们一个重要启示：**XA-Guard 三件套（MCP Server + Protocol + SDK）本身就是"多形态"的优秀设计**，不需要再叠加一个完整 SaaS 形态。

---

## 5. "如果我们做 XA-Guard SaaS 会怎样"——具体推演

### 5.1 技术可行性

- 用 FastAPI / Flask 写个 `/v2/check` endpoint 给 agent 调用：**学生 1 周可写出 MVP**。
- 6 关卡（门口安检 / 办事大厅 / 规则引擎 / 信息流污点 / 隔离沙箱 / 黑匣子审计）的核心逻辑可以"按 HTTP 调用粒度"重组：每次 agent 工具调用前调一次 `/check`。
- 后端可以照搬 Lakera 的接口设计（OpenAI chat completions 兼容请求体）。

### 5.2 但马上撞到的现实问题

1. **基础设施债务**：
   - SaaS 必须 24x7 在线 → 学生团队赛事完成后没人维护，3 个月后必挂。
   - 要做 HTTPS 证书 / 防 DDoS / 速率限制 / 监控告警。
   - 评审 demo 那天云服务挂了 = 零分。
   - 单一域名 endpoint 是单点故障。

2. **政企"数据出网"质疑**：
   - 评委一个问题可以让所有"SaaS 形态"叙事崩塌："那我政务办公的 prompt 都被你这个学生团队的服务器看到了？数据出境备案过吗？等保过吗？"
   - 这个质疑**无法被回答**。

3. **同质化风险**：
   - "学生团队做了个山寨版 Lakera Guard" → 创新性 25% 这部分被打折。
   - Lakera 都被 Check Point 收购了，市面上已经有 5 家以上同形态商业产品。

4. **与现有三件套定位冲突**：
   - 三件套已经把"协议中立 / 客户端无关"作为核心叙事（implementation-notes 里反复强调）。
   - 突然多一个 SaaS 形态会让"产品锚点"模糊。

5. **不是国际/学术研究前沿**：
   - 学术界（NDSS/ICLR/USENIX 等）正在研究的是 **CaMeL / IsolateGPT / AgentSpec / ShieldAgent** 这种"中间策略层"的能力 —— 这些**几乎全部是"以 library / runtime / proxy"形态**，**没有任何一篇是把"外置 SaaS"作为核心创新点**的（参见 reference/02_tool_security/）。

### 5.3 与 MCP Server 形态的对比叙事

- MCP Server 形态在评委面前的叙事："蹭 Anthropic 协议生态 / 协议中立 / 客户端无关 / 改一行配置即生效 / 自部署在客户内网 / 兼容 Trae/CodeBuddy/通义灵码等国产生态"。
- 外置 SaaS 形态：**没有任何一条叙事点能比上面这套强**。

### 5.4 例外：何时 SaaS 形态有意义

- 如果做的是 **"评测/红队 as a Service"**（如 CalypsoAI 的 Inference Red-Team），那确实适合 SaaS —— 因为红队评测**结果数据可脱敏**，不涉及生产业务数据。
- 在我们的 XA-Bench 评测套件层面**可以**考虑做一个"对外开放评测 endpoint"作为加分项 —— 但这个不属于核心防护链路。

---

## 6. 客观结论：值不值得选 SaaS 形态？

### 6.1 直接回答

**不值得作为主推形态**。建议维持 MCP Server 主推 + Protocol + SDK 三件套的现有规划。

### 6.2 三条核心理由

1. **政企客户的"私有化天花板"** —— 60% 企业 + 几乎 100% 央国企会拒绝外置 SaaS。GB/T 45654 数据分级和等保 2.0 都是硬约束。商业上活下来的 Lakera / Cisco / 阿里 / 腾讯 / 360 全部支持自托管/私有化，**没有纯 SaaS 路线的赢家**。
2. **学生团队的"基础设施承担能力"** —— 24x7 SaaS 是工程债务陷阱。MCP Server 客户自部署，我们交付即终结。
3. **创新性叙事的稀释** —— MCP Server 三件套已经是清晰的产品锚点，叠加 SaaS 形态会让方案"看起来更全面但实际上更糊"。学术前沿（CaMeL / IsolateGPT / AgentSpec / ShieldAgent）也都是 runtime / library 形态，没人在做"SaaS 学术研究"。

### 6.3 但可以考虑保留的"SaaS 形态痕迹"

- **三件套中的 SDK** 已经覆盖了"app 直接调用安全检查函数"的需求 —— 这就是 SaaS HTTP API 的等价物（只不过是同进程，不是网络调用）。
- 如果一定要给评委展示"我们也有外置服务能力"，可以**在 SDK 内部默认 in-process，留一个 `mode="remote"` 配置项**，把同样的函数封装成 HTTP 调用。这样有"形态完整"的展示价值，但不需要真的把 SaaS 跑 24x7。
- **XA-Bench 评测可以做一个"对外评测 endpoint"作为 nice-to-have**（不影响核心赛道分）。

### 6.4 风险对冲（如果用户仍坚持要 SaaS 形态）

如果团队最终决定增加 SaaS 形态，**最小工作量方案**：
1. 用 Vercel / Cloudflare Workers 免费层托管一个 `/check` endpoint（不要自管服务器，绝对免维护）。
2. 后端逻辑完全复用 MCP Server 的 6 关卡代码（共享 core library，only 改输入/输出层）。
3. 评审 demo 时**只演示一次调用**作为"形态完整性"证据，不作为主线。
4. 在方案里明确写："SaaS 形态作为'快速对接'选项，**核心交付仍为 MCP Server + 私有化部署**"。

### 6.5 给团队的最后一句话

> "**Lakera 用 4 年时间做到了 200+ 企业客户、Dropbox 标杆案例，最后还是被 Check Point 收购了，因为'独立 SaaS' 在企业级 AI 安全市场不够强壮。学生团队 4 个月做一个简化版的 Lakera，是把自己放在了一个'国际同质化、国内不被接受、运维不可持续'的形态上。坚守 MCP Server 三件套是对的选择。**"

---

## 参考来源

[1] [Lakera API Overview](https://docs.lakera.ai/docs/api) — Lakera 官方 API 文档
[2] [Lakera Pricing Tiers](https://www.eesel.ai/blog/lakera-pricing) — 第三方价格分析
[3] [Lakera Guard 2026 Review](https://appsecsanta.com/lakera) — 检出率、延迟、客户数据
[4] [Lakera Customers Page](https://www.lakera.ai/customers) — Dropbox 案例
[5] [Check Point Acquires Lakera](https://www.checkpoint.com/press-releases/check-point-acquires-lakera-to-deliver-end-to-end-ai-security-for-enterprises/) — 收购公告
[6] [CalypsoAI Official](https://calypsoai.com/) — 产品形态 + Palantir / DoD 合作
[7] [Lockheed Martin AI Strategy](https://www.klover.ai/lockheed-martin-ai-strategy-analysis-of-dominance-in-aerospace-defense/) — Lockheed 投资逻辑 + 自身 LMText 本地化
[8] [Robust Intelligence Cool Vendor](https://blogs.cisco.com/ai/robust-intelligence-now-part-of-cisco-recognized-as-a-2024-gartner-cool-vendor-for-ai-security) — Cisco 收购前荣誉
[9] [Cisco AI Defense Data Sheet](https://www.cisco.com/c/en/us/products/collateral/security/ai-defense/ai-defense-ds.html) — Inspection API + Gateway + AI POD 多形态
[10] [Protect AI Layer Product](https://protectai.com/layer) — 30+ 策略 runtime D&R
[11] [HiddenLayer AISec 2.0](https://hiddenlayer.com/innovation-hub/hiddenlayer-unveils-aisec-platform-2-0-to-deliver-unmatched-context-visibility-and-observability-for-enterprise-ai-security/) — Agentless + 35+ 格式
[12] [HiddenLayer Platform](https://hiddenlayer.com/aisec-platform/) — 非侵入式定位
[13] [百度千帆 4.0 安全白皮书](https://news.pedaily.cn/20250915/114298.shtml) — 混合云专线 + 6 维度防护
[14] [阿里云 AI 安全护栏](https://help.aliyun.com/document_detail/2873209.html) — 5 大能力 + 配置文档
[15] [腾讯云 AI 安全风险评估框架](https://news.sina.com.cn/sx/2025-09-30/detail-infshafs8080410.shtml) — LLM-WAF + AI-SPM + 天御网关
[16] [智谱招股书背景](https://m.bjnews.com.cn/detail/1766243288129791.html) — 私有化 + MaaS 双轨
[17] [360 大模型安全](https://360.net/product-center/security-intelligence-brain/360secllm) — 公有云 + 私有化双轨
[18] [360 IDC 实测第一](https://360.net/mobile/about/news/article67510bd16ddf08001f91a733) — 国内排名
[19] [大模型私有化 AB 面](https://www.stcn.com/article/detail/1582536.html) — 60% 私有化数据 + 中国 SaaS 现状
[20] [大模型内容安全私有化市场](https://blog.csdn.net/weixin_51109776/article/details/147896062) — 5 亿规模 + 1/10 私有化占比
[21] [2025 等保实施分析](https://blog.csdn.net/2403_86962125/article/details/148141485) — 责任分担 + 测评要求
[22] [DeepSeek 本地化部署法律风险](https://www.guantao.com/page4163) — 数据出境标准
[23] [政企 AI Agent 智能体研究报告](https://www.smartcity.team/reports/2b2g-ai-agent-report/) — 三条实施路径
[24] [Cequence: LLM Proxies vs MCP Gateways](https://www.cequence.ai/blog/ai/mcp-gateway-vs-llm-proxy/) — 形态对比
[25] [Noma: AI Gateways vs MCP Gateways](https://noma.security/blog/ai-gateways-vs-mcp-gateways-what-security-teams-need-to-know/) — 安全视角
[26] [Cisco AI Defense Inspection API](https://developer.cisco.com/docs/ai-defense-inspection/introduction/) — API 形态文档
[27] [F5 收购 CalypsoAI](https://www.geekwire.com/2025/f5-paying-180m-to-acquire-calypsoai-to-boost-ai-enterprise-security-offerings/) — 1.8 亿美金交易
[28] [Protect AI 被 Palo Alto 收购](https://protectai.com/) — Prisma AIRS 整合
[29] [央国企大模型采购规模](https://www.53ai.com/news/LargeLanguageModel/2024072197142.html) — 几百万至千万规模

---

*完。预计字数 4200 字。如果团队对结论有疑问或需要进一步对比某一形态的工程细节，可加 issue 单独讨论。*
