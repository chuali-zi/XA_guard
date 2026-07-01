# 备选产品形态 · 外置 SaaS / HTTP API 方案

> **文档定位**：产品形态可行性评估的**备选方案 #3**。当前主推 MCP Server 形态，本文评估"用外置 SaaS / HTTP API 服务作为主形态或补充形态"的可行性。
>
> **结论先看**：**强烈不推荐。无论作为主形态还是补充形态，对政企学生赛道都是反向选择。**
>
> **详细调研报告**：[./research-raw/saas-form.md](./research-raw/saas-form.md)（约 4200 字 + 29 个引用来源）

---

## 1. 外置 SaaS 是什么

**外置 SaaS / HTTP API 形态**：把安全检测逻辑部署在一个外部服务上，agent 通过 HTTP/HTTPS 调用这个 endpoint 做安全检查。

```
[Agent 应用]
    ↓ HTTP POST https://xa-guard.example.com/v1/check
    ↓ { "input": "...", "tool": "..." }
    ↓
[我们的 SaaS 服务（云端）]
    ↓ 返回 { "decision": "allow", "risks": [] }
    ↓
[Agent 应用决定放行或拦截]
```

**与 MCP Server 的区别**：
- **MCP Server**：协议层透明代理（agent 不知道有"安全层"）
- **外置 SaaS**：应用层显式调用（agent 必须主动发请求）

---

## 2. 业界代表产品（全部被收购）

| 产品 | 收购情况 | 时间 | 收购方 |
|---|---|---|---|
| **Lakera Guard** | 被收购 | 2025 | Check Point |
| **CalypsoAI** | 被收购 | 2025 | F5（约 $1.8 亿） |
| **Robust Intelligence** | 被收购 | 2024-08 | Cisco |
| **Protect AI** | 被收购 | 2025 | Palo Alto Networks |
| **Hidden Layer** | 独立 | — | — |

**关键发现**：**纯 SaaS 安全产品的赛道全部被吸收进大厂网络安全板块**。这强烈暗示 **SaaS 不是终局形态**。

**Lakera Guard 的旗舰客户 Dropbox**——为什么选 Lakera？

**关键原因**：Lakera 提供**自托管 Docker 镜像**（不是纯 SaaS）。Dropbox 不愿把数据发到第三方云。

---

## 3. 国产同类产品（无一做纯 SaaS）

| 厂商 | 产品 | 形态 |
|---|---|---|
| 百度智能云 | 大模型安全护栏 | **私有化部署 + 一体机 + 端侧 SDK** |
| 阿里云 | AI 安全护栏 | 云端 SaaS（仅一个云，配合百炼）+ 企业级私有化 |
| 腾讯云 | AI 安全 | 私有化 + 云端 |
| 智谱 | 安全方案 | 私有化为主 |
| 360 | 大模型安全 | 私有化 + 一体机 |

**关键发现**：**国产 5 大厂没有一家做纯 SaaS**——全部是"私有化部署为主，SaaS 作为补充"。

理由很简单：**政企客户不会把推理数据交给第三方云**。

---

## 4. 政企采购的天花板

### 4.1 60% 企业本地化

公开调研显示：**60% 大型企业的 AI 应用要求本地化部署**，央国企接近 100% 拒绝纯外置 SaaS。

### 4.2 合规硬约束

**GB/T 45654-2025**（生成式 AI 服务安全基本要求）：
- 训练数据、推理数据**不应跨境**
- 涉敏感数据时**应支持私有化部署**

**等保 2.0 三级**：
- 重要业务数据**不应离开等保系统边界**

**大模型内容安全市场盘子**（2024-2025）：
- 总盘约 5 亿/年
- **私有化部分约 5000 万/年**（占比约 10%）
- 纯 SaaS 部分几乎可以忽略不计

### 4.3 演示与评审视角

**雄安比赛是政企赛题**——评委多来自政企背景。"外置 SaaS"在政企语境里**几乎等于"数据出域"**——是个负面词。

---

## 5. 学生团队不能承担 SaaS 运维

### 5.1 24x7 SaaS 是债务陷阱

如果做了 SaaS，意味着：
- 要持续运维（云服务费、监控、故障响应）
- 答辩**演示视频录制那天**云服务挂掉 = 0 分
- 比赛交付后，**SaaS 还要继续跑**（不然评委复核会失败）

### 5.2 学生团队可负担的现实

- 2-3 人小队，5 个月时间
- 没有商业云预算（最多自费一两台云主机）
- 无法保证 24x7 SLA

**做 SaaS 是项目自杀路径**。

---

## 6. 学术前沿也不是 SaaS 路线

我们文献库 [literature/](../literature) 里的核心防御研究：

| 论文 | 形态 |
|---|---|
| **CaMeL** (DeepMind 2025) | Python library / interpreter |
| **IsolateGPT** (NDSS 2025) | runtime architecture |
| **AgentSpec** (ICSE 2026) | runtime enforcement |
| **ShieldAgent** (ICML 2025) | runtime verifier |
| **LlamaFirewall** (Meta 2025) | Python SDK |
| **GuardAgent** | code-generated guardrail |

**没有一篇是 SaaS 形态**。学术界都走 library / runtime 路线，因为**研究价值在算法**，不在部署模式。

---

## 7. 风险对冲：如果用户仍想保留 SaaS 痕迹

如果团队**就是想保留 SaaS 可能性**，可以在 SDK 留一个 `mode="remote"` 配置项：

```python
from xa_guard import Guard

# 本地模式（默认）：所有检测本地跑
guard = Guard(policy="enterprise-l3")

# 远程模式（可选）：检测发到 SaaS endpoint
guard = Guard(
    policy="enterprise-l3",
    mode="remote",
    endpoint="https://xa-guard.example.com"  # 默认空，需配置
)
```

**好处**：
- 30 页方案里可以提："我们的 SDK 同时支持本地和远程模式"
- 不需要真的部署 24x7 SaaS
- 评委问"未来 SaaS 化路径"时有答案

**坏处**：
- 这只是个"留白"，不构成实际差异化
- **不要花工程时间真的搭一个云端 endpoint**

---

## 8. 客观结论

| 选项 | 评估 |
|---|---|
| SaaS 替换 MCP 作为主形态 | ❌ **强烈不推荐** |
| SaaS 作为补充加分项 | ❌ **不推荐**（运维债务 > 加分价值） |
| SDK 留 `mode="remote"` 配置（仅留白）| ⭕ **可做，0 成本** |
| 完全不提 SaaS | ⭕ **也合理** |

### 推荐方案
**完全不做 SaaS**。如果担心评委问到，**SDK 留 `mode="remote"` 配置项作为"未来扩展接口"**——0 成本，话术上有应对。

### 给评委 Q&A 的弹药

当被问"为什么不做 SaaS"时，**三条回答**：

1. **政企不允许**：60% 企业要求本地化、央国企近 100% 拒绝；GB/T 45654 + 等保 2.0 是硬约束
2. **商业市场无纯 SaaS 赢家**：Lakera / CalypsoAI / Robust Intelligence / Protect AI 全部被收购，国产 5 大厂没一家做纯 SaaS
3. **学术也不走 SaaS 路线**：CaMeL / IsolateGPT / AgentSpec / ShieldAgent / LlamaFirewall 全是 library / runtime

---

## 9. 与"安全外置服务"直觉的关系

用户提到的"**安全外置服务**"概念——**和 MCP Server 本质上是同一件事**：
- MCP Server 也是"外置"的（独立进程 / 独立服务）
- 只是它用 **MCP 协议**通信，而不是 HTTP API

**用 MCP 比 HTTP API 好的原因**：
- 蹭 Anthropic + 国产 AI 工具生态（Trae / CodeBuddy / 通义灵码全支持）
- 不需要每个 agent 应用都写 HTTP 调用代码
- 协议中立，客户端无关

所以**我们其实已经在做"安全外置服务"**，只是选了一个比 HTTP API 更聪明的协议。

---

## 10. 与现有方案的关系

- **MCP Server**（主形态）：[产品架构.md](../../planning/产品架构.md)
- **Skill 方案**（备选）：[产品形态-备选-Skill方案.md](./产品形态-备选-Skill方案.md)
- **CLI/SDK 方案**（备选）：[产品形态-备选-CLI方案.md](./产品形态-备选-CLI方案.md)
- **横向对比 + 最终推荐**：[产品形态-对比分析.md](./产品形态-对比分析.md)

详细调研报告：[./research-raw/saas-form.md](./research-raw/saas-form.md)
