# 下一步工作设计

> 快照：2026-06-30 20:xx PDT
> 目标：把“接下来开始做什么”固定为一份可执行工作设计，不再让 PRD、TODO、status、研究资料互相打架。
> 状态标签：`DONE` / `PARTIAL` / `BLOCKED` / `TODO` / `REFERENCE`

## 1. 当前总体结论

仓库现在不是空壳，核心安全原型已经有相当多实现：六关卡、MCP 代理、审计、AIBOM、R2/R3 预算 runner、Agent Governance v1 都在主线里。

但比赛交付还没有闭环。当前只能谨慎写成：

> L3 静态实现验收通过 + 部分真实环境验收通过 + D2 原型主体具备；L3 最终验收、正式 R2/R3 sampled 指标、D1/D3/D4 交付物仍未完成。

## 2. 官方 D1-D4 状态

| 交付物 | 状态 | 下一步 |
|---|---|---|
| D1 技术方案 PDF | `TODO` | 在 [../delivery/D1-technical-report-draft.md](../delivery/D1-technical-report-draft.md) 写 30 页以内草稿，只引用已有证据 |
| D2 原型代码/仓库 | `PARTIAL` | 保持 clean main，准备 release freeze、复现命令、artifact hash |
| D3 演示视频 | `TODO` | 按 [../delivery/D3-video-script.md](../delivery/D3-video-script.md) 录 10 分钟以内视频 |
| D4 审核通过报名表 | `BLOCKED` | 人工确认报名系统审核状态，仓库内不要伪造证据 |
| 可选补充材料 | `PARTIAL` | 用 [../delivery/submission-checklist.md](../delivery/submission-checklist.md) 收束证据目录、hash、截图、邮件附件 |

## 3. 四个赛题方向状态

| 方向 | 当前状态 | 可写入 D1 的边界 |
|---|---|---|
| 方向 1：复杂输入链路攻击识别 | `PARTIAL` | Gate1、Spotlighting、规则/模型接入和 holdout 协议有实现/文档；正式独立 holdout 未完成 |
| 方向 2：工具调用与任务执行安全 | `PARTIAL/BLOCKED` | Gate2/3/4/5、HITL/pending、策略和污点有实现；真实 Trae GUI 和 Linux gVisor 仍阻塞 |
| 方向 3：插件/Skill/脚本供应链 | `PARTIAL/BLOCKED` | 内部 AIBOM gateway、外部 cdxgen CycloneDX 1.6 交换、CLI 准入和离线 install_plugin 准入链已有；真实 marketplace/IDE native 安装 hook 未完成 |
| 方向 4：评测、审计溯源、持续优化 | `PARTIAL` | XA-Bench、AgentDojo/InjecAgent adapter、预算 runner、Gate6 审计链已有；正式 `$60` sampled 实跑和第三方 TSA/HSM 未完成 |

## 4. L3 / R1-R9 状态

| 项 | 状态 | 下一步 |
|---|---|---|
| L3 静态实现验收 | `DONE` | 可作为工程成熟度证据，但不能写最终 L3 PASS |
| R1 双 500 / holdout | `BLOCKED` | 需要独立评测方、封存数据和 threshold lock |
| R2/R3 外部 benchmark | `TODO/BLOCKED` | 先 dry-run，再单独授权 `$60` 预算内 sampled 实跑 |
| R4 性能 | `DONE/PARTIAL` | 已有历史性能证据；最终提交前建议复跑 |
| R5 Trae | `BLOCKED` | 需要真实 Trae GUI 截图/录像 |
| R6 gVisor | `BLOCKED` | 需要 Linux/runsc 环境 |
| R7 OPA | `DONE/PARTIAL` | parity/fail-closed 已有；镜像漏洞仍需 approved digest 或风险接受 |
| R8 外部 AIBOM | `DONE/PARTIAL` | 合法外部生成器产物、CLI 准入和离线 install_plugin 准入链已通过；marketplace/IDE native hook 未完成 |
| R9 第三方 TSA/HSM | `LIMIT/BLOCKED` | external signer bridge 已有；第三方 TSA/HSM provider 未配置，本地 TSA/软件 key 只能作为 demo/CI |

## 5. P0 执行顺序

1. 确认 D4 报名审核状态，拿到审核通过截图或明确写 blocked。
2. 基于 [../delivery/D1-technical-report-draft.md](../delivery/D1-technical-report-draft.md) 起草 D1，不写未验证结论。
3. 基于 [../delivery/D3-video-script.md](../delivery/D3-video-script.md) 准备 demo 数据、审计目录和录屏。
4. 跑不花钱验证：全仓 pytest、L3 static verifier、R2/R3 budget dry-run、链接检查。
5. 收束 D2 提交包：clean commit、README 复现路径、artifact hash、证据索引。
6. 若用户单独授权，再跑 R2/R3 `$60` sampled 校准和主评测。

## 6. P1 / P2 后续路线

| 优先级 | 工作 | 说明 |
|---|---|---|
| P1 | 真实 Trae / 支持 elicitation 客户端演示 | 增强方向 2 展示可信度 |
| P1 | marketplace/IDE native 安装 hook | 在已有外部 AIBOM/离线准入基础上增强方向 3 真实性 |
| P1 | Linux gVisor runsc 证据 | 增强沙箱可信度 |
| P1 | 第三方 TSA/HSM 或明确 blocked | 增强政企证据链可信度 |
| P2 | Agent Governance 管理 API / SSO | 当前 v1 是本地 YAML + 静态控制台 |
| P2 | 多 Agent 委托链治理 | 可进入决赛增强，不应写成本轮已完成 |
| P2 | Undo/补偿元数据 | 可作为未来工作 |

## 7. 不可夸大声明清单

- 不写“L3 最终验收通过”。
- 不写“R2/R3 指标已达标”，除非 `$60` sampled 真实跑完并聚合。
- 不把 2,986-job full matrix 写成比赛必需或已完成。
- 不把 Trae fallback 写成 native elicitation。
- 不把本地 TSA/软件 SM2 key 写成第三方 TSA/HSM。
- 不把内部 AIBOM exporter 写成合法外部 AIBOM 生成器。
- 不把 Agent Governance v1 写成生产 IAM/SSO/RBAC。
- 不把 FORCE 会议照片里的外部事实未经核验写成正式引用。

## 8. 实施者默认口径

- 任何新数字必须能回到脚本输出、审计日志、证据 JSON 或 artifact hash。
- `status.md` 描述当前仓库状态，不写历史流水账。
- `log.md` 只在顶部追加客观工作记录。
- 需要费用、外部系统、真实 GUI 或生产 key 的事项，必须单独授权或标记 `BLOCKED`。
