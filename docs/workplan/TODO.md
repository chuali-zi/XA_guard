# XA-Guard 下一步 TODO 与交付收束计划

> 快照时间：2026-06-30 20:xx PDT（docs 物理重构后）
> 适用目录：`D:\race\XA_guard\jiebang`
> 最高依据：`docs/source-of-truth/XA-202620中国雄安集团数字城市科技有限公司-面向政企场景的大模型智能体安全关键技术研究比赛方案.pdf`
> 配套状态文件：`../../status.md`
> 本文件目标：把“现在是什么状态”和“下一步具体做什么”放在一个可执行入口里。

## 0. 先读结论

当前仓库的主要矛盾已经不是“有没有安全原型”，而是“比赛交付证据还没有收束”。

- 代码层：XA-Guard 六关卡、bench、审计、AIBOM、Docker/OPA/gVisor 静态配置、R2/R3 预算型 runner、Agent Governance v1 已经很完整。
- 证据层：L3 静态验收通过，部分真实验收通过，但真实 Trae、Linux gVisor、外部 AIBOM、第三方 TSA/HSM、R2/R3 sampled 正式结果、R1 独立 holdout 仍未闭环。
- 交付层：仓库内没有发现 D1 技术方案 PDF 成稿、D3 演示视频、D4 审核通过报名表证据。官方交付最看重这三件和可复现代码链接。
- 文档层：`docs/` 已完成物理重构。顶层只保留 `docs/README.md`，本 TODO 已迁入 `docs/workplan/`；后续工作设计见 [NEXT-WORK-DESIGN.md](./NEXT-WORK-DESIGN.md)。

**下一步第一优先级**：确认 D4 报名表是否已经在 2026-06-30 截止前系统审核通过。仓库没有证据能证明这一点，这是人工事项，不是代码事项。

## 1. 官方赛题要求复核

| 赛题原文要求 | 仓库对应 | 当前判断 | 下一步 |
|---|---|---|---|
| 技术方案报告 PDF，原则上不超过 30 页 | `docs/planning/PRD.md`、`docs/planning/产品架构.md`、`docs/planning/项目总览.md`、`docs/research/force-ai-security-2026/` 可作为素材 | 未发现最终 D1 PDF 成稿 | 立刻起草 30 页以内 D1，所有数字只写已有证据或明确标注待测 |
| 原型系统或核心算法代码，可复现关键技术验证结果，并提供运行说明、部署说明或代码仓库链接 | 根 `README.md`、`docker-compose.yml`、`configs/`、`scripts/`、`tests/` | D2 代码主体已具备，仍需最终 clean worktree、证据包和部署复验 | 做 release freeze、跑验证、生成 artifact hash 和最终说明 |
| 演示视频，不超过 10 分钟，展示核心功能、关键流程和测试效果 | `frontend/`、`demo/`、`docs/planning/产品架构.md`、`docs/delivery/D3-video-script.md` | 未发现最终视频 | 按 10 分钟脚本录制，至少覆盖拦截、污点、审批、治理、审计、评测 |
| 报名表，系统审核通过版，信息与系统一致 | 仓库无报名表证据 | 状态未知，且报名期为 2026-05-30 到 2026-06-30 | 人工确认系统审核状态和盖章扫描件 |
| 可选补充材料：测试数据、评测脚本、攻击样例、审计日志样例 | `bench/`、`docs/evidence/`、`scripts/verify_audit.py`、`HACK-BENCH` 文档 | 已有大量素材，但尚未形成提交包索引 | 做 `artifact-hashes.json`、证据目录说明和提交邮件附件清单 |

评分维度对当前重点的含义：

| 评分维度 | 权重 | 当前最该补的证据 |
|---|---:|---|
| 实际效果 | 30% | R2/R3 sampled 指标、CSAB-Gov-mini 报告、真实 demo trace、误报/漏报和延迟 |
| 技术创新性 | 25% | Agent Gateway 叙事、双层 Policy DSL、三色污点、国密审计链、预算型 benchmark 方法 |
| 方案完整性 | 20% | 四方向映射、D1 结构、部署说明、限制与未来工作 |
| 应用价值 | 20% | 等保、GB/T 45654、国密、政企内网、Trae 国产生态、审计追责 |
| 展示表达 | 5% | 10 分钟视频、图表、答辩话术、不要夸大未验收项 |

## 2. 当前状态分层

### 2.1 可以比较有底气写入 D1/D2 的内容

- XA-Guard 是一个双面 MCP 安全代理：上游作为 MCP Server，下游作为 MCP Client。
- 六关卡链路已经有工程实现：Gate1 输入检测，Gate2 HITL/pending，Gate3 策略，Gate4 污点，Gate5 沙箱路由，Gate6 审计。
- 双层 Policy DSL 已落地 baseline + overlay + 单调性门控 + `bundle_sha` 入审计。
- 290 条 CSAB-Gov-mini seed 回归、双 500 candidate、AgentDojo/InjecAgent adapter、R2/R3 预算型总控器都已存在。
- 审计链支持 SM3/SM2、本地 TSA anchor、篡改检测、faithfulness v1 重算。
- Docker Compose、OPA、gVisor、Trae 配置模板和静态 verifier 已有。
- 2026-06-22 工作树记录过 `PYTHONUTF8=1` 下全仓 `584 passed, 1 skipped`，统一静态 verifier 11/11 PASS。

### 2.2 必须谨慎写边界的内容

- 不能写“L3 最终验收通过”。当前只能写“L3 静态实现验收通过 + 部分真实验收通过”。
- 不能把 2,986-job AgentDojo/InjecAgent 全矩阵当比赛必需。它是研究级扩展。
- 不能把 `subscription_budget60_v1` 工具实现写成“R2/R3 指标已达标”。新的 `$60` 正式校准和主评测还没有跑完。
- 不能把 Trae 原生 elicitation 写成已验证。Trae 静态模板有，真实 GUI 截图/录像未补。
- 不能把本地 TSA、软件 SM2 key 写成第三方 TSA/HSM。
- 不能把内部 AIBOM exporter 写成合法外部 AIBOM 生成器。
- 不能直接把 `docs/research/force-ai-security-2026/` 的外部事件和数字当正式引用。那是现场照片整理，正式引用前需要二次核验。

## 3. P0 - 官方交付必做

这些是影响 2026-09-15 提交的主线任务。优先级高于研究级优化。

### P0.1 立刻确认 D4 报名状态

**原因**：报名开放期是 2026-05-30 到 2026-06-30。当前本机时间是 2026-06-30 19:28 PDT，按中国时间已经接近或越过截止窗口，仓库没有报名表证据。

- [ ] 登录 `2026.tiaozhanbei.net` 或官方报名系统，确认作品是否已报名。
- [ ] 确认报名表是否已下载、盖章、扫描并上传。
- [ ] 确认系统审核状态是“审核通过”，不是“待审核”或“驳回”。
- [ ] 核对报名表信息和系统填报信息完全一致。
- [ ] 保存本地证据：审核通过截图、盖章扫描件、提交时间截图。
- [ ] 决定这些个人/学校信息是否只放仓库外提交包，不进入 Git。

完成标准：

- 有审核通过证据。
- D4 不再被 `status.md` 写成“仓库未发现证据”。
- 若未报名成功，立即停止后续“参赛提交”假设，转为补救沟通或内部项目路线。

### P0.2 收束 Git 状态和工作区归属

状态：`DONE`。当前主线是 `D:\race\XA_guard\jiebang` 的 `main` 分支；此前重复的 `jiebang-agent-governance` worktree 已合并、清理，Agent Governance v1 已进入 main 并推送远端。

- [x] 在 `D:\race\XA_guard\jiebang` 执行 `git status --short`，列出所有变更。
- [x] 把当前 `jiebang` 作为唯一提交主线。
- [x] 合并 Agent Governance v1 到 main。
- [x] 清理重复 worktree 和过期本地分支。
- [ ] 正式跑 R2/R3 或做 release 前，必须形成 clean worktree 或明确记录 dirty hash。
- [ ] 不修改测试代码来掩盖失败；测试确实有问题时先单独提请审核。

完成标准：

- 有一个明确主线目录和主线分支。
- `status.md` 中的 HEAD、dirty 状态、证据路径与实际一致。
- D1/D2/D3 不再引用两个分支互相冲突的能力。

### P0.3 生成 D1 技术方案 PDF 的正文骨架

建议从 Markdown 起草，最后转 PDF。30 页以内，不要把所有 docs 内容都塞进去。

建议章节：

1. 摘要：一句话、四方向覆盖、核心创新、当前实测结论和边界。
2. 赛题问题分析：多源输入攻击、工具调用越权、供应链、审计治理。
3. 总体架构：XA-Guard Agent Gateway、双面 MCP 代理、六关卡、下游工具。
4. 关键技术一：复杂输入链路检测，Gate1 + Spotlighting + 规则/模型融合。
5. 关键技术二：工具调用安全控制，Gate2/Gate3/Gate4/Gate5。
6. 关键技术三：插件/Skill/脚本供应链，AIBOM 准入和边界。
7. 关键技术四：评测、审计和国密证据链。
8. 实验设计和结果：CSAB-Gov-mini、R2/R3 sampled、性能、审计验链。
9. 政企落地价值：等保、GB/T 45654、国密、国产 IDE、私有化部署。
10. 当前限制和未来工作：独立 holdout、Trae、gVisor、外部 AIBOM、TSA/HSM。

写作 TODO：

- [x] 先建 D1 草稿文件：[../delivery/D1-technical-report-draft.md](../delivery/D1-technical-report-draft.md)，不要直接在 PRD 上改。
- [ ] 用赛题 PDF 的四方向作为章节锚点，避免只写内部 L3 口径。
- [ ] 每个技术点后面都写“当前实现证据”和“未完成边界”。
- [ ] 图表至少准备 10 张草图：总架构、六 Gate、Agent Gateway、Policy DSL、污点传播、沙箱、审计链、benchmark 流程、提交物关系、风险矩阵。
- [ ] 数字只引用已有证据：测试数、性能、预算、样本数、覆盖率。
- [ ] 所有未跑完的内容写成“计划/待验”，不要写成“已完成”。
- [ ] 加红线检查：学校名、个人名、不规范地图、敏感凭据、API key。
- [ ] 最后导出 PDF，检查页数 <= 30。

完成标准：

- 有可审阅的 30 页以内 PDF。
- 每个量化结果都能回到脚本、日志或证据文件。
- 限制章节说清楚，不影响可信度。

### P0.4 准备 D2 原型系统代码提交包

- [ ] 确认公开 GitHub/Gitee 链接或 access token 策略。
- [ ] 根 `README.md` 保持可复现 quick start，不要只写叙事。
- [ ] 复跑基础验证：
  - [ ] `PYTHONUTF8=1 python -m pytest -q`
  - [ ] `PYTHONUTF8=1 python scripts/verify_l3_static.py --section all`
  - [ ] `python -m ruff check ...` 针对变更文件
  - [ ] Docker daemon 可用时跑 `scripts/verify_l3_deployment.py --run-build --run-up`
- [ ] 生成最终环境记录：OS、Python、Docker、commit、dirty 状态、依赖锁。
- [ ] 生成 artifact hash manifest，覆盖 README、configs、scripts、docs、证据文件和关键报告。
- [ ] 检查 `.gitignore`，确保日志、密钥、个人信息、OpenCode 配置不入库。
- [ ] 准备一页“复现路径”：如何启动、如何跑 demo、如何验审计链、如何看前端。

完成标准：

- 评审者能按 README 跑通最小 demo。
- D2 代码和 D1 文字里的命令一致。
- 所有外部依赖许可证和来源可解释。

### P0.5 录制 D3 演示视频

建议 9 分钟 30 秒以内，留 30 秒缓冲。

视频结构：

| 时间 | 内容 | 必须出现的证据 |
|---|---|---|
| 0:00-0:30 | 项目一句话和赛题四方向 | XA-Guard Agent Gateway 总图 |
| 0:30-1:30 | 攻击背景和政企场景 | 运维助手、文件、工具、权限 |
| 1:30-2:45 | 间接注入拦截 | 恶意文档、Gate1/Gate3/Gate6 trace |
| 2:45-4:00 | 数据泄露/污点阻断 | CONFIDENTIAL 到外部工具被阻断 |
| 4:00-5:15 | 高危操作审批 | Trae 基础 MCP 或 fallback；若用 Cursor 弹窗，明确说明 |
| 5:15-6:30 | 沙箱/部署 | Docker Compose、healthz、沙箱边界 |
| 6:30-7:45 | 审计回放 | 前端时间线、SM3/SM2、verify_audit |
| 7:45-8:45 | 评测结果 | CSAB-Gov-mini、R2/R3 sampled 或待测说明、性能 |
| 8:45-9:30 | 总结和落地价值 | 等保、国密、国产生态、限制 |

录制 TODO：

- [ ] 先写逐句旁白稿，所有数字与 D1 一致。
- [ ] 准备干净 demo 数据和审计目录。
- [ ] Trae 如果无法原生 elicitation，不要硬演；用 pending fallback 或支持 elicitation 的客户端作为审批镜头。
- [ ] 屏幕不要出现学校名、真实姓名、API key、OpenCode token、个人路径中的敏感信息。
- [ ] 保留原始视频、剪辑工程、导出文件和 hash。
- [ ] 给最终视频加字幕。

完成标准：

- 视频小于 10 分钟。
- 至少展示 3 个真实可复现场景。
- 视频中的每个“已实现”都有代码或审计证据支撑。

### P0.6 准备最终提交邮件和附件清单

官方提交邮箱：`caoruyue@chinaxiongan.com.cn`。赛题 PDF 写的邮件命名规范是 `[揭榜挂帅·心理智能体]+学校+团队负责人姓名`，这可能是模板遗留，但正式提交前应按 PDF 原文或咨询结果执行。

- [ ] 确认邮件主题格式。
- [ ] 附件/链接包含：
  - [ ] D1 技术方案 PDF。
  - [ ] D2 代码仓库链接和访问说明。
  - [ ] D3 演示视频或网盘链接。
  - [ ] D4 系统审核通过报名表。
  - [ ] 可选补充材料目录。
- [ ] 网盘链接设置有效期到决赛后，避免初审期间失效。
- [ ] 邮件正文写清楚题号 XA-202620 和题目名称，避免“心理智能体”模板混淆。
- [ ] 提交后保存已发送邮件、时间戳、回执和网盘访问截图。

完成标准：

- 2026-09-15 24:00 前完成提交。
- 提交包可从另一台机器打开和下载。

## 4. P0 - 四个赛题方向的证据收束

### 4.1 方向 1：复杂输入链路攻击识别与风险评估

当前资产：

- Gate1 规则检测、Spotlighting、模型检测后端壳。
- `docs/gates/gate1-real-model-verification.md`
- `docs/gates/gate1-holdout-protocol.md`
- 双 500 candidate 语料。
- CSAB-Gov-mini seed。

必须补：

- [ ] 明确 D1 里 Gate1 当前主路线：规则 + Spotlighting 为主，Qwen3Guard 当前是接入链路/对照，不要夸大真实效果。
- [ ] 复查 `gate1-real-model-verification.md` 的最新结果，挑能写入 D1 的数字。
- [ ] R1 独立 holdout 如果短期做不了，在 D1 中写成“独立评测待完成”，不要写正式 Recall/FPR。
- [ ] 双 500 candidate 只能写 implementation profile，不能写 formal 成绩。
- [ ] 给 D3 视频准备 1 个间接注入场景，要求有审计 trace。

完成标准：

- D1 有方向 1 章节。
- 已有结果和未完成 formal holdout 分开写。

### 4.2 方向 2：工具调用和任务执行安全约束

当前资产：

- Gate2 风险分级和 pending approval。
- Gate3 双层 Policy DSL。
- Gate4 三色污点。
- Gate5 Docker/gVisor 沙箱配置。
- Trae 静态模板。

必须补：

- [ ] 真实 Trae 四案例：allow、deny、taint、pending。
- [ ] 如果 Trae 不支持 native elicitation，记录 fallback，不要写成 native 弹窗。
- [ ] Linux 主机上跑 gVisor/runsc 证据；如果短期没有 Linux 主机，就写成外部环境 blocker。
- [ ] OPA 固定镜像 provenance/license、漂移负测和完整 fixture 矩阵，能跑多少写多少。
- [ ] D3 视频至少展示 Gate2/Gate3/Gate4 的差异，不要只给一个“deny”。

完成标准：

- 有真实客户端或真实运行时证据支撑方向 2。
- 每个 deny/approval 都能从审计链复核。

### 4.3 方向 3：插件、Skill 与脚本供应链安全

当前资产：

- AIBOM gateway。
- 本地 artifact/hash 和离线镜像扫描。
- CycloneDX 1.6 导入适配。
- `docs/acceptance/L3-aibom-external-generator.md`

必须补：

- [ ] 选择一个合法合规的外部 AIBOM 生成器或明确写“未选定外部生成器”。
- [ ] 记录外部工具名称、版本、许可证、来源、命令和输出 hash。
- [ ] 生成 benign、高风险、篡改、缺字段样本各 1 个。
- [ ] 跑 `python -m xa_guard.aibom.cli validate <external-bom.json>` 和 `admit <artifact>`。
- [ ] 做 hash mismatch / 缺字段 / 高风险 deny 负测。
- [ ] 若无法接真实 marketplace/IDE 安装链，D1 写“离线准入原型”，不要写“商店拦截已完成”。

完成标准：

- 方向 3 至少有一个外部 BOM 交换证据，或明确列为未完成边界。
- D1 中供应链章节能支撑“覆盖方向 3”，但不冒充完整生产链。

### 4.4 方向 4：评测、审计溯源和持续优化

当前资产：

- XA-Bench / CSAB-Gov-mini。
- AgentDojo/InjecAgent adapter 和 `subscription_budget60_v1`。
- Gate6 审计链、SM3/SM2、本地 TSA、faithfulness。
- 前端时间线。

必须补：

- [ ] `subscription_budget60_v1` 新输出目录跑 `budget-plan`。
- [ ] `budget-run --phase calibration --dry-run`，确认每批最多 8 jobs 和续考顺序。
- [ ] 获得单独付费授权后再移除 `--dry-run`，先跑 `$6` calibration。
- [ ] `budget-freeze` 成功后才跑 main；如果预算不足，写 `INCONCLUSIVE_BUDGET`。
- [ ] `budget-aggregate` 输出 sampled report，点估计和置信区间分开写。
- [ ] 生成 `sampled-artifact-hashes.json`。
- [ ] 复跑 `scripts/verify_audit.py`，准备 D3 审计回放。
- [ ] 如果第三方 TSA/HSM 不具备，D1 写本地 TSA/软件 key 的 demo 边界。

完成标准：

- 方向 4 有可复核指标和审计证据。
- sampled 结果不被写成 full matrix 或官方排行榜成绩。

## 5. P1 - L3 真实验收补证

这些会显著增强 D1/D2/D3，但如果外部条件不足，应如实写 blocked。

| 项 | 为什么重要 | 下一步动作 | 外部依赖 |
|---|---|---|---|
| R1 formal 双 500 + Gate1 holdout | 证明输入检测不是开发集自嗨 | 找独立评测人封存数据和 threshold lock | 独立评测方 |
| R5 真实 Trae GUI | 国产生态硬承诺 | 按 `docs/acceptance/L3-trae-static-integration.md` 录屏和验审计 | Trae 客户端 |
| R6 Linux/gVisor runsc | 证明沙箱不是静态配置 | 在 Linux 主机安装 runsc，跑 no-egress/readonly/rootless 负测 | Linux 主机 |
| R7 OPA 完整 parity | 策略引擎可信 | 固定 OPA image digest，跑全 fixture 和 drift 负测 | OPA 镜像/二进制 |
| R8 外部 AIBOM | 方向 3 真实性 | 选定合法外部生成器并归档 BOM | 外部工具 |
| R9 第三方 TSA/HSM | 政企证据链可信 | 接第三方 TSA 或 HSM/KMS，跑断连/PIN/篡改负测 | 生产式密钥/服务 |
| Faithfulness 大规模重放 | 防止审计字段占位 | 对真实 agent trace 独立重算 | 独立重放脚本/样本 |

## 6. P2 - 决赛和加分路线

这些不是 9 月提交前必须完成，但适合进入未来工作或决赛打磨。

- [x] 合并 Agent Governance v1：Agent identity、运行时治理预检、`gen_ai.governance.*` 审计、静态治理控制台。
- [x] 在项目叙事中把 XA-Guard 补充为 Agent Gateway，而不是“过滤器集合”。
- [x] 增加“第三类身份”基础字段：human principal、agent identity、task、data domain、resource owner。
- [x] Capability Token 审计摘要化：白名单字段保留，secret/token/signature 只落 hash。
- [ ] 补工具组合风险测试：单工具 allow 但组合越权、RAG 隐藏指令到外发工具、审批拒绝后仍不得执行后续工具。
- [ ] 补 Undo/补偿元数据：`side_effect_level`、`reversible`、`undo_tool`、`compensation_hint`。
- [ ] 做 CodeBuddy / Qoder CN 基础 MCP 接入验证。
- [ ] 如果资源允许，做 `research_full_matrix` 或本地/免费模型替代评测。

## 7. docs 整理状态

### 7.1 已完成的物理重构

状态：`DONE`。`docs/` 顶层现在只保留 `README.md`，其他顶层文档已按职责迁入分类目录。

```text
docs/
├── README.md
├── source-of-truth/
│   ├── 事实源.md
│   └── XA-202620...比赛方案.pdf
├── planning/
│   ├── PRD.md
│   ├── 产品架构.md
│   └── 项目总览.md
├── workplan/
│   ├── TODO.md
│   └── NEXT-WORK-DESIGN.md
├── acceptance/
│   ├── L2-acceptance-checklist.md
│   ├── L2-verification-commands.md
│   ├── L3-test-and-acceptance.md
│   ├── R2-R3矩阵自动验收使用说明.md
│   └── R2-R3完整矩阵预算分析.md
├── gates/
│   ├── gate1-real-model-verification.md
│   ├── gate1-holdout-protocol.md
│   ├── Gate2-3-4策略审核指南.md
│   └── L3-trae-static-integration.md
├── bench-redteam/
├── delivery/
│   ├── D1-technical-report-draft.md
│   ├── D3-video-script.md
│   └── submission-checklist.md
├── evidence/
├── tutorials/
└── references/
```

### 7.2 后续维护要求

- 新增交付文件放 `docs/delivery/`。
- 新增工作安排放 `docs/workplan/`。
- 新增验收说明放 `docs/acceptance/`。
- 新增 Gate 级策略/风险说明放 `docs/gates/`。
- 新增研究资料放 `docs/research/` 或 `docs/references/`。
- 移动文件后必须跑链接检查，并更新 `docs/README.md`。

### 7.3 旧顶层文档现在的位置

| 文档 | 当前位置 | 状态 |
|---|---|---|
| `TODO.md` | `docs/workplan/TODO.md` | `TODO` |
| `事实源.md` | `docs/source-of-truth/事实源.md` | `DONE` |
| `PRD.md` | `docs/planning/PRD.md` | `PARTIAL` |
| `产品架构.md` | `docs/planning/产品架构.md` | `PARTIAL` |
| `项目总览.md` | `docs/planning/项目总览.md` | `REFERENCE` |
| `L3-test-and-acceptance.md` | `docs/acceptance/L3-test-and-acceptance.md` | `PARTIAL/BLOCKED` |
| `R2-R3*.md` | `docs/acceptance/` | `TODO/BLOCKED` |
| `HACK-BENCH-组员提交规范.md` | `docs/bench-redteam/` | `REFERENCE` |
| `XA-Bench-对抗测试规则.md` | `docs/bench-redteam/` | `REFERENCE` |
| `force-ai-security-2026/` | `docs/research/force-ai-security-2026/` | `REFERENCE` |

## 8. 建议的执行顺序

### 第 0 步：当天立即做

1. 确认 D4 报名是否审核通过。
2. 检查当前工作树，确认 release 前 clean。
3. 基于 `docs/delivery/` 完成 D1 草稿和 D3 视频脚本。
4. 按 `docs/workplan/NEXT-WORK-DESIGN.md` 执行 P0。

### 第 1 步：不花钱验证

1. 跑全仓测试和 L3 static verifier。
2. 跑 R2/R3 `budget-plan` 和 calibration `--dry-run`。
3. 跑 Docker build/up healthz，如果当前机器支持。
4. 生成一版本地证据目录和 hash manifest。

### 第 2 步：真实证据补齐

1. Trae 四案例截图/录像。
2. R2/R3 `$6` calibration 和 sampled 主评测。
3. 外部 AIBOM 生成器样本。
4. Linux gVisor 或明确 blocked。
5. 第三方 TSA/HSM 或明确 blocked。

### 第 3 步：交付物写作和剪辑

1. 用已经有证据的数字写 D1。
2. 用真实录屏剪 D3。
3. 根 README 和 docs README 做最终导航。
4. 形成提交包清单。

### 第 4 步：提交前红线复检

- [ ] PDF 不超过 30 页。
- [ ] 视频不超过 10 分钟。
- [ ] 没有学校名/个人隐私/密钥/Token。
- [ ] 所有链接可访问。
- [ ] 所有数字在证据包里能找到来源。
- [ ] 所有未完成项都写成限制，不写成已完成。
- [ ] 邮件在 2026-09-15 24:00 前发送。

## 9. 不要做清单

- [ ] 不要为了好看修改测试代码。
- [ ] 不要把旧 `$10` 首批 7 个 complete 结果混入新正式 sampled 分母。
- [ ] 不要把 `--max-jobs` 前缀运行冒充分层抽样。
- [ ] 不要把 `research_full_matrix` 当比赛硬 blocker。
- [ ] 不要把 force-ai-security 照片整理中的外部事实未经核验写进正式引用。
- [ ] 不要把本地 TSA/软件 key 写成第三方 TSA/HSM。
- [ ] 不要把 Trae fallback 写成 native elicitation。
- [ ] 不要在提交包里暴露 API key、OpenCode 配置、operator token 或个人联系方式以外的隐私。

## 10. 最小完成定义

如果时间紧，最低可接受的比赛交付闭环是：

- D4 已审核通过。
- D2 代码可运行，README 可复现，核心测试和静态 verifier 有最新结果。
- D1 PDF 能完整解释四方向覆盖、架构、实验、结果、限制。
- D3 视频展示至少三个真实链路：拦截、审批/阻断、审计回放。
- 有一个证据目录：测试输出、性能报告、审计样例、artifact hash、截图/视频 hash。
- 未完成的外部依赖全部明确写成 blocked 或 future work。

这个闭环比“继续追求全矩阵或所有外部生产级设施”更重要。
