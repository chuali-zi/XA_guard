# D1 技术方案报告草稿

> 目标：最终导出为 30 页以内 PDF。
> 交付口径：[../acceptance/DELIVERY-v2.md](../acceptance/DELIVERY-v2.md)
> 写作原则：主实验 = Open Agent Range A/B + 六关 demo/audit；只写已有证据；退役项写 out-of-scope，不写 blocker。
> 赛题依据：[../source-of-truth/XA-202620中国雄安集团数字城市科技有限公司-面向政企场景的大模型智能体安全关键技术研究比赛方案.pdf](../source-of-truth/XA-202620中国雄安集团数字城市科技有限公司-面向政企场景的大模型智能体安全关键技术研究比赛方案.pdf)

## 1. 摘要

- 项目一句话：XA-Guard 是面向政企智能体的 Agent Gateway：绑定“谁委托哪个 Agent”，让真实副作用可受控补偿并留下完整证据。
- 覆盖方向：输入攻击识别、工具执行约束、供应链安全、评测审计溯源。
- 主评测结论：Open Agent Range 企业场景竖切下，Null vs XA-Guard live A/B 观测到可复核的 `protection_delta`；六关卡 demo 与审计链可回放。
- 当前边界：D1/D3/D4 交付物进行中；不以 AgentDojo ASR 或 budget60 作为本文达标声明。

## 2. 问题分析

- 多源输入攻击：提示注入、RAG 投毒、间接注入、工具输出污染。
- 工具调用风险：越权、敏感数据外发、高危操作无人审批。
- 插件/Skill 供应链风险：恶意包、篡改、能力声明缺失。
- 政企验收风险：审计不可回放、责任归属不清、证据链不可信。

## 3. 总体架构

- XA-Guard MCP Server：对 IDE/智能体暴露安全代理。
- XA-Guard MCP Client：连接真实下游工具。
- 六关卡：Gate1 输入、Gate2 审批、Gate3 策略、Gate4 污点、Gate5 沙箱、Gate6 审计。
- Agent Governance v1：员工、Agent、数据域、预算和审批的本地治理预检（默认关闭）。
- Open Agent Range：独立企业红队靶场，XA-Guard 作为 live SUT，产出 Tier B 主证据。

### 3.1 主创新：从登录身份到可恢复 Agent 行为

传统 IAM 只回答谁登录，传统审计只回答发生了什么。XA-Guard 把责任链和恢复链接到同一条实际执行路径：

```text
human sub -> Agent act.sub/azp -> tenant -> dynamic assignment ∩ YAML ceiling
          -> XA-Guard Gate1–6 -> prepared Effect -> business side effect
          -> independent approval -> signed compensation -> Gate1–6 -> evidence
```

核心差异包括：

- **human→agent 双主体链**：浏览器用 Authorization Code + PKCE；BFF 代表已登录人员执行 Standard Token Exchange，Agent token 不进入浏览器持久存储。
- **动态 Agent assignment**：human/group 可用哪些 Agent、Agent 可用哪些工具/数据域存入 PostgreSQL；每次调用都与静态 ceiling 重新相交，撤销立即生效。
- **intent-first Effect**：写操作先登记 `prepared`，再用 `effect_id` 作为下游幂等键；数据库不可用时下游执行数必须为零。
- **补偿状态机与职责分离**：申请人与审批人不能是同一 `sub`；批准后由独立 lease Worker 重新经过治理和六关执行补偿。
- **诚实恢复语义**：不可逆动作进入 `manual_required`；系统声明“至少一次调度 + 下游幂等有效一次”，不宣称绝对 exactly-once 或通用数据库回滚。

对照设计：

| 组别 | 身份链 | 副作用恢复 | 证据能力 | 预期问题 |
|---|---|---|---|---|
| Null / 无 Identity | 仅客户端自报或共享账号 | 无 | 业务日志零散 | 无法证明谁委托哪个 Agent，越权在执行前不可可靠拒绝 |
| 只有审计 | 可记录 human/Agent 字段 | 无 | 能回答发生了什么 | 已发生错误副作用无法进入受控恢复闭环 |
| Identity + Undo | OIDC 双主体 + 实时 assignment | v2 合同 + 独立审批 + Worker | 原 trace、补偿 trace、Effect/Gate6 两条链 | 在可逆合同边界内同时实现事前授权、事中六关、事后恢复 |

Reference Compose 已通过 Alice/Dora 的真实 PKCE + token exchange 协议链和工单 `open -> cancelled`；交互式浏览器录屏、故障注入全集、并发 p95 与 kind 多副本仍未完成，因此当前口径是 `CORE-IMPLEMENTED / REFERENCE-VALIDATION-IN-PROGRESS`，不是生产落地声明。

## 4. 关键技术一：复杂输入链路攻击识别

- 已有：规则检测、Spotlighting、模型后端接入、CSAB-Gov-mini 290 seed。
- 可写证据：[../gates/gate1-real-model-verification.md](../gates/gate1-real-model-verification.md)；OAR 注入面与 Gate1 联动 demo。
- 边界：独立 holdout / formal dual-500（原 R1）**已退役**；holdout 协议仅研究资产，不写正式 Recall/FPR。

## 5. 关键技术二：工具调用与任务执行安全

- 已有：Gate2 风险分级、HITL/pending、Gate3 policy、Gate4 taint、Gate5 沙箱、Docker deploy。
- 可写证据：L3 静态 verifier、MCP e2e、审计日志；OAR seat/SUT/ToolSurface 全链路。
- 边界：Trae native elicitation、gVisor runsc 全验收 **已退役** 为硬承诺；演示可用 pending fallback 与支持 elicitation 的客户端。

## 6. 关键技术三：插件与供应链安全

- 已有：AIBOM gateway、离线准入、cdxgen CycloneDX 1.6 导入、`xa-aibom validate/admit`、离线 `install_plugin`。
- 可写证据：[../acceptance/L3-aibom-external-generator.md](../acceptance/L3-aibom-external-generator.md)、R8 acceptance 目录。
- 边界：marketplace/IDE native hook **已退役**；OAR supply/plugin consequence 作场景补充。

## 7. 关键技术四：评测、审计与持续优化

- **主实验叙事**：Open Agent Range — 企业 full-day 场景、hash ledger、`replay --verify-sut-audit`、Null vs XA-Guard live A/B。
- 已有：Gate6 SM3/SM2、本地 TSA anchor、faithfulness v1；XA-Bench/CSAB-Gov-mini；bench 工具链（含 AgentDojo adapter，**附录可选**）。
- 可写证据：`open-agent-range/` 下 `protection_delta=1.0` live A/B、`sut-session.json`、replay alignment JSON。
- 边界：`subscription_budget60_v1` **已退役** 为比赛 Must；若附录提及 R2/R3，仅写工具存在与背景实验，不写指标达标。

## 8. 实验设计和结果

**主表（写入正文）**：

| 实验 | 状态 | 可写结论 | 证据 |
|---|---|---|---|
| OAR Null vs XA-Guard live A/B | `DONE` | N=3：null 3/3 泄漏、xaguard 3/3 拦截、0 infra error、`protection_delta=1.0` | `oar-delivery-v2-20260711T123124Z-win-local` |
| OAR full-day + ledger replay | `DONE` | 41 tool attempts、43 ledger、0 violations；7/7 attempt replay PASS | [证据总表](../acceptance/EVIDENCE-CONSOLIDATION.md) |
| 六关 demo + verify_audit | `DONE` | 拦截、审批、污点、审计闭环 | `demo/`、`scripts/verify_audit.py` |
| L3 static S1–S7 | `DONE` | 静态实现与验收入口齐备 | status / evidence |
| R4 性能 | `DONE` | 10 会话达 PRD 中等档 | `docs/evidence/l3-r4-20260705-current/` |

**附录表（可选，不欠赛题）**：

| 实验 | 状态 | 说明 |
|---|---|---|
| R7 OPA parity | `DONE` | 64 fixtures 一致 |
| R8 cdxgen + install_plugin | `DONE` | 方向 3 交换证据 |
| R2/R3 budget60 sampled | `RETIRED` | 工具保留；未跑不写达标 |
| AgentDojo/InjecAgent 全矩阵 | `RETIRED` | 2986 jobs 研究扩展 |

### Open Agent Range 附录要点（建议 §8 末或独立小节）

- 场景：`scenarios/dctg/full-day.json` 六域正常日；F3/F10/F11/F13/F14 等业务链。
- SUT：attempt 级真实 `xa_guard.server` stdio MCP session（`sut-session.json`）。
- 指标：`protection_delta`、violations、external sends、ledger projection。
- 复现：见 [DELIVERY-v2 § OAR 命令块](../acceptance/DELIVERY-v2.md#可复现-oar-证据命令canonical)。
- 封存：`D:/xa-evidence/sealed/oar-delivery-v2-20260711T123124Z-win-local.tar.gz`，SHA-256 `cffa89fb2ded79cb17685348bfb6571d85c3c233ad963528ca79b89e2ec49aa5`。
- 限制：ReactiveSeat 为确定性状态机；非完整 7×24 工业沙盘。

## 9. 政企落地价值

- 私有化部署：MCP 代理、Docker Compose、策略 overlay。
- 合规对齐：等保、GB/T 45654（290 seed 为 PoC 缩减）、国密审计、OpenTelemetry GenAI 字段。
- 责任归属：human principal、agent id、data domain、task id、approval token、audit hash。
- 红队与持续改进：OAR workbench 支持 finding、A/B、promote 与证据审阅。

## 10. 当前限制与未来工作（out-of-scope，非 blocker）

以下项 **不** 构成本文或比赛交付的失败条件：

- R1 独立 holdout / formal dual-500
- `subscription_budget60_v1` / `research_full_matrix` 2986 jobs 作为 mandatory 指标
- R9 第三方 TSA/HSM 生产实证（本地 demo 已够叙事）
- R8 marketplace/IDE hooks
- R6 gVisor runsc 全验收（Docker deploy PASS 已够）
- R5 Trae native elicitation
- GB/T 45654 完整 500+ 语料
- enterprise-agent-range 主叙事（已并入 OAR）
- 外部 notarization

**真实待完成**：D1 PDF 定稿、D2 clean release freeze、D3 视频、D4 报名。canonical OAR 证据封存（B5）已完成。

## 11. 红线检查

- 不写未验证达标数字。
- 不暴露 token、key、个人隐私。
- 不把本地 demo 写成第三方生产服务。
- 不把「L3 最终 BLOCKED」写成项目主状态。
- PDF 最终页数不超过 30 页。
