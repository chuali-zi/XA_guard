# 仓库状态 · XA-Guard / XA-202620

更新时间：2026-05-31 14:40 +08:00
维护者：Codex 主 agent

## 总体判断

当前仓库是 **demo MVP / M1 末到 M2 前的可运行骨架**，已经能表达赛题方案的主线：用双面 MCP 代理把 LLM 客户端和下游工具隔开，在中间串 6 个安全关卡，并用 XA-Bench 与审计日志提供演示证据。

但它还不是 PRD 目标里的 L3 政企原型。现在最适合定位为“可跑、可演示、可继续扩展的安全中台雏形”。有些漏洞和空白是正常的，因为 README/PRD 也明确当前处于 demo 阶段；关键是后续开发不能把这些 demo fallback 写成已完成能力。

## 与赛题 4 个方向的贴合度

| 赛题方向 | 当前仓库状态 | 空位 / 未完成 |
|---|---|---|
| 方向 1：复杂输入链路攻击识别 | `gate1_input.py` 已有规则版检测和可插拔 detector 壳子，能扫提示注入、越狱、系统提示套取、PII/SQL/shell 等危险模式；有单元测试。 | Qwen3Guard / ShieldLM 等真实模型权重尚未接入，Spotlighting 默认未启用，也没有 Recall@1%FPR 和 adaptive attack 评测。RAG 投毒/网页间接注入仍主要是规则级识别。 |
| 方向 2：工具调用与任务执行安全 | `gate2` 风险分级、`gate3` Python 策略规则、`gate4` 三色污点、`gate5` 沙箱路由决策都已存在；pipeline 已能让 Gate3 的 DENY 覆盖 Gate2 的 REQUIRE_APPROVAL；上游已接最小 MCP elicitation approve/reject 路径，toy 协议 probe 跑通。 | 真实 Cursor / Claude Code / Codex 弹窗 UI 仍未人工实测；国产客户端仍只能按事实源写 fallback；OPA Rego backend 未实现；Docker/gVisor 真实沙箱未执行，只输出路由；Policy 只有 10 条 seed，距离 PRD 至少 30 条规则还有差距。 |
| 方向 3：插件 / Skill / 脚本供应链安全 | `src/xa_guard/aibom/` 已有可演示闭环：Python AST 危险 API/import 扫描、JSON/YAML 元数据扫描、依赖风险解析、A/B/C/D/F 评级、CycloneDX-like 导出、本地 artifact/file URL/zip/tar 解包、sha256 provenance、typosquat 启发式、AIBOM drift 比较；bench 的 4 条 supply_chain seed 已全过。 | 不联网下载远程包；没有外部包信誉库；没有真实签名体系、公钥校验、Sigstore/TUF；CycloneDX 是 like JSON，未做 schema 校验；上线后漂移监测仍是离线比较函数。 |
| 方向 4：评测与审计溯源 | `Gate6Audit`、Merkle/哈希链、OTel 字段、`bench` CLI、HTML report、frontend 时间线都已存在；测试覆盖了审计、bench、proxy smoke；损坏的历史 `logs/audit/audit.jsonl` 已归档，新的主日志已重新开始且 verify 0 错。 | 当前 bench 仍是 30 条 seed regression：普通 case 使用 mock executor，供应链 seed 走简化评级路径；`audit_completeness` 固定为 1.0，不是 bench 实测。SM3/SM2 是 fallback，CoT 忠实度字段也是占位。距离 PRD 290 条 PoC 目标还很远。 |

## 当前可用能力

- Python 包骨架与 CLI 存在：`xa-guard` / `xa-bench` entry points 已配置。
- 6 个 gate 文件都有实现，不是完全空目录。
- `Pipeline` 能串起 gate1 → gate2 → gate4(in) → gate3 → gate5 → executor → gate4(out) → gate6。
- stdio 上游 MCP server 与 stdio 下游 MCP client 已有 smoke 测试。
- demo target 和 3 个演示脚本存在，可用于展示间接注入、数据外泄、HITL fallback。
- 评测工具能跑 30 条 seed case，并写出 `bench/.log/last_results.json`、`last_report.json`、`report.html`。
- 已新增组员 hack 提交规范、维护者对抗测试规则、机器可校验 JSON Schema 和 runner-compatible YAML 模板。
- 前端是离线审计时间线，不是完整管理后台，但可以做演示素材。

## 主要空壳 / 占位清单

1. **SDK 是空的**：`sdk/decorators.py` 的 `@protect` 只透传原函数，没有 mini-pipeline、LangChain callback、Guard session。
2. **AIBOM 还是本地/离线 MVP**：已补 CycloneDX-like 导出、本地 artifact 解包、sha256 provenance、typosquat 和 drift；但未做外部信誉库、真实签名体系和生产级 CycloneDX schema 校验。
3. **MCP elicitation 仍缺真实客户端 UI 证据**：toy MCP 协议 probe 已跑通，`proxy/upstream.py` 有最小接入；但 Cursor / Claude Code / Codex 的实际弹窗和人工点击记录还没完成。
4. **Streamable HTTP 未实现**：上游 `run_streamable_http()` 直接 `NotImplementedError`；下游也只支持 stdio。
5. **OPA / Rego 未实现**：`gate3_policy.py` 的 `backend=rego` 会抛 `NotImplementedError`；当前是受限 Python predicate。
6. **Docker / gVisor 未执行**：`gate5_sandbox.py` 只给 `sandbox_mode`，没有实际把工具调用放进容器。
7. **历史审计链已归档为损坏样本**：旧主日志被移动到 `logs/audit/archive/audit-20260528T104349214385Z.jsonl`，manifest 记录 1146 条、34 个链错误、首错第 401 行；新的主日志已重新开始并验链通过。
8. **国密证据链不完整**：SM3/SM2 依赖 gmssl fallback；没有 TSA；签名也不是正式 SM2 私钥流程。
9. **CoT 忠实度未实做**：审计字段里有 `faithfulness_score=1.0`，但没有解释性/忠实度检测算法。
10. **评测规模不足**：当前 30 条 seed，PRD Must 是 290 条 CSAB-Gov-mini；国标完整题库要求更高，只能声明 PoC。
11. **Protocol PDF / 技术方案 / 演示视频未交付**：代码仓库有 docs，但比赛必交的 30 页技术方案 PDF、10 分钟视频、报名表不在仓库内完成。
12. **XA-Bench 指标可信度仍需 hardening**：当前 `audit_completeness=1.0` 是固定值；CuP 只是非阻断代理指标；ASR / Recall 会混入合法审批治理动作；pipeline 异常会被 runner 静默吞掉。
13. **XA-Bench 还不是 MCP E2E bench**：普通 case 直接构造 `GateContext` 并使用 mock executor；真实 MCP stdio、审批恢复、多步工具链仍需独立 harness。
14. **供应链 seed 是简化路径**：4 条 `install_plugin` case 走 `rate_install_request()`，不覆盖完整本地 artifact 解包、provenance、导出、drift，也不进入 Gate6 审计。
15. **interpretability seed 只是 smoke**：`INTP-001` 不是 CoT faithfulness 算法实测。

## 最新验证结果

本次维护时重新执行：

- `PYTHONPATH=src python -m pytest -q`：通过，全量测试绿。
- 用临时 audit 目录跑 `bench/cases/csab-gov-mini-seed.yaml` 并刷新 `bench/.log/last_results.json` / `last_report.json` / `report.html`：通过运行，最新指标如下。
- `PYTHONPATH=src python scripts/probe_mcp_elicitation.py` 和 `--reject`：均通过，触发 1 次 toy elicitation event，approve 返回 `approved: hello`，reject 返回 `rejected`。
- `PYTHONPATH=src python scripts/archive_audit.py --path logs/audit/audit.jsonl --reason known-corrupt-sample --create-empty`：已执行真实归档，manifest 记录 1146 条旧日志、34 个链错误、首错第 401 行。
- `PYTHONPATH=src python scripts/verify_audit.py --path logs/audit/audit.jsonl`：通过，当前新主日志 35 条记录、0 个链错误、0 条缺字段。
- `PYTHONPATH=src python scripts/verify_audit.py --path <temp-bench-audit>/audit.jsonl`：通过，26 条新写入记录 0 个链错误，0 条缺字段。

最新 bench 指标：

| 指标 | 最新值 | 说明 |
|---|---:|---|
| total | 30 | 仍是 seed，不是 PRD 290 用例 |
| pass_rate | 96.67% | 30 条 seed 中仍有 1 条 exact mismatch：DATA-003 |
| legacy seed ASR | 0.0% | 当前按 `expected_decision != allow` 推导攻击集合，会混入治理动作；不能等同 AgentDojo / InjecAgent ASR |
| legacy seed Recall | 100.0% | 当前是 `1 - legacy seed ASR`；不能等同模型 Recall@FPR，也不能外推到 PRD 290 条 |
| FPR | 0.0% | 新口径下 WARN 不算阻断；exact pass 仍会记录 allow/warn 不一致 |
| CuP proxy | 100.0% | 当前只是合法样例非阻断率，不验证真实任务完成 |
| Latency P50 / P95 | 2.91 ms / 6.02 ms | 当前是规则 pipeline + mock executor，不能代表真实 MCP、模型推理或沙箱性能 |
| audit_completeness | 占位 100% | bench 目前固定写 `1.0`，不能作为实测；独立 `verify_audit.py` 对指定新日志样本可验 |

最新仍未 exact pass 的 case：

- `DATA-003`：期望 `allow`，实际 `warn`。根因是 `send_notification` 是 yellow 工具，Gate2 发异步通知 WARN；这是“可执行但提示”的产品语义，指标 FPR/CuP 已按非阻断处理，exact pass 保留差异。

## 距离 PRD 目标的差距

PRD 默认目标是“进取 + 冲刺”，代码交付目标是 L3 政企原型。当前更接近 L1/L2 之间：

- L1 基础：基本满足 demo 口径。6 关卡核心代码可跑，测试存在，AIBOM MVP 已补上；但多个关卡仍是规则/fallback/路由决策。
- L2 工程：部分满足。README、测试、bench、demo 都有，README 指标已同步最新 seed；审计归档入口和 toy HITL probe 已补，但 coverage 数字未跑。
- L3 政企：未达到。Docker 一键部署、真实国密、Trae 实测、OPA、290 用例、真实 HITL、完整合规映射都还缺。
- L4 工业：未开始。CI/CD、监控告警、多客户端实测、生产部署都不是当前状态。

## Gate 1 模型选型留痕（2026-05-27 子 agent 调研结论）

PRD M2 原计划用 **PromptGuard 2 中文微调 + Llama Guard 3**，经四路 web search 调研后建议**改弦**：

**结论：放弃 Meta 系做主分类器，改用国产开源直接拉，无需微调。**

| 原计划 | 调研发现 | 决定 |
|---|---|---|
| PromptGuard 2 (86M/22M) | 中文不在官方评测七语种内，HF 无中文微调版；字符级绕过实测 100%；512 token 上限 | 不作主力，可作英文/国际模式第二层 |
| Llama Guard 3 (8B/1B) | 中文不在官方八语种内，HF 无中文微调版；S1–S14 类目与政企场景契合度仅 ~50%；许可 Llama Community License 需标注 | 不作主力 |
| **Qwen3Guard-Gen (0.6B/4B/8B)** | **Apache 2.0**，原生 119 语言含中文，28 类含「越狱」「政治敏感」独立类目，Stream 变体 token 级流式，阿里背书；0.6B CPU 可跑 | **主选**：0.6B 做 CPU 旁路 + 4B/8B 做主判 |
| **ShieldLM-14B-qwen** | **MIT**，清华 CoAI / EMNLP 2024，中英双语原生，三分类 + 可解释理由输出（答辩友好） | **备选/可解释层**：14B-qwen 商用 OK；6B-chatglm3 仅研究用 |

**间接注入（赛题方向 1 真正难点）无开箱方案**：学术 SOTA 是 Microsoft Spotlighting（prompt 标记法，ASR >50%→<2%）和 InstructDetector（白盒，不适配我们黑盒架构）。务实路径：
1. 规则层（现有 `gate1_input.py` 保留）+ Unicode 归一化/零宽字符过滤
2. **Spotlighting 标记**：非用户源包 `<untrusted_source>...`，对接现有 `InputSource` 标签
3. **Qwen3Guard-Gen-0.6B** 旁路三分类，对接 `Decision.ALLOW/WARN/DENY`
4. （加分项）AlignmentCheck：比对用户意图 vs agent 准备执行的 action

**中文评测数据集**（M4 扩 290 条用得上，全部开源）：SafetyBench / CValues / JADE / FLAMES / SC-Safety / CHiSafetyBench / Do-Not-Answer 中文版。

**已知风险**：Qwen3Guard 在 hand-crafted 对抗样本上准确率仅 33.8%（疑似过拟合公开 benchmark），不能裸用，必须配合规则层 + Spotlighting 多层防御。

**待动作**：
- 同步更新 `docs/PRD.md` M2 章节"PromptGuard 2 + Llama Guard 3" → "Qwen3Guard + Spotlighting + 规则"
- 同步更新 README L235 已知不全表
- 技术验证：先拉 Qwen3Guard-Gen-0.6B 在 30 条 seed 上跑一遍 Pass Rate 对比

详细调研报告：4 个子 agent 输出（Prompt Guard 2 / Llama Guard 3 / 中文模型横向 / 间接注入与 RAG 投毒），可向主 agent 索取原文。

## 下一步优先级

1. **XA-Bench hardening**：按 `docs/XA-Bench-对抗测试规则.md` 实现 `case_kind` 分桶、显式 `infra_error`、taint / rule hit / audit assertion 和真实 audit completeness。
2. **开始 HACK-BENCH triage**：让 hack 组员按 `docs/HACK-BENCH-组员提交规范.md` 提交第一批 candidate，优先补 runner 异常一致性、审批拒绝后零执行、审计篡改和多步污染链。
3. **真实客户端 HITL 弹窗实测**：toy MCP 协议 probe 已跑通；下一步必须在 Cursor / Claude Code / Codex 中完成真实 UI 弹窗、approve/reject 点击和记录截图/日志。国产客户端仍按事实源写 fallback，不夸大。
4. **Gate2 审批令牌与审计增强**：当前 approve 后会走 `run_after_approval()`，但还没有 approval_token、审批人、审批理由入审计字段。
5. **AIBOM 生产化**：补 CycloneDX schema 校验、Sigstore/TUF 或本地公钥签名、远程包离线拉取工作流、外部信誉库/漏洞库、持续漂移监测任务。
6. **扩 Policy DSL 到 30 条，扩 CSAB-Gov-mini 到 290 条**：围绕等保 2.0、GB/T 45654 的 31 类生成内容切片和 17 类拒答切片补规则、单测和样例。
