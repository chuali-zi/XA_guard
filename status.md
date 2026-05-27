# 仓库状态 · XA-Guard / XA-202620

更新时间：2026-05-27 23:41 +08:00  
维护者：Codex 主 agent

## 总体判断

当前仓库是 **demo MVP / M1 末到 M2 前的可运行骨架**，已经能表达赛题方案的主线：用双面 MCP 代理把 LLM 客户端和下游工具隔开，在中间串 6 个安全关卡，并用 XA-Bench 与审计日志提供演示证据。

但它还不是 PRD 目标里的 L3 政企原型。现在最适合定位为“可跑、可演示、可继续扩展的安全中台雏形”。有些漏洞和空白是正常的，因为 README/PRD 也明确当前处于 demo 阶段；关键是后续开发不能把这些 demo fallback 写成已完成能力。

## 与赛题 4 个方向的贴合度

| 赛题方向 | 当前仓库状态 | 空位 / 未完成 |
|---|---|---|
| 方向 1：复杂输入链路攻击识别 | `gate1_input.py` 已有规则版检测，能扫提示注入、越狱、系统提示套取、PII/SQL/shell 等危险模式；有单元测试。 | 还没有 PromptGuard 2 / Llama Guard 3 真实推理，也没有中文微调样本与 Recall@1%FPR 评测。RAG 投毒/网页间接注入仍是关键词规则，不是模型级识别。 |
| 方向 2：工具调用与任务执行安全 | `gate2` 风险分级、`gate3` Python 策略规则、`gate4` 三色污点、`gate5` 沙箱路由决策都已存在；pipeline 已能在 DENY / REQUIRE_APPROVAL 时阻断 executor。 | HITL 还没有接 MCP elicitation，只有 stdout/deny/async fallback；OPA Rego backend 未实现；Docker/gVisor 真实沙箱未执行，只输出路由；Policy 只有 10 条 seed，距离 PRD 至少 30 条规则还有差距。 |
| 方向 3：插件 / Skill / 脚本供应链安全 | `src/xa_guard/aibom/` 有 scanner/rater 接口，bench 里有 supply_chain 维度。 | 基本是空壳：scanner 只做元数据级占位，rater 固定返回 `C, stub`；没有 AST 扫描、依赖风险、CycloneDX/AIBOM、签名校验、漂移监测。当前供应链维度是最大短板。 |
| 方向 4：评测与审计溯源 | `Gate6Audit`、Merkle/哈希链、OTel 字段、`bench` CLI、HTML report、frontend 时间线都已存在；测试覆盖了审计、bench、proxy smoke。 | 审计链当前验证失败；SM3/SM2 是 gmssl 可选 + HMAC/SHA256 fallback，不是完整国密证据链；CoT 忠实度字段固定占位，解释性没有真实算法；CSAB-Gov-mini 当前只有 30 条 seed，距离 PRD 290 条 PoC 目标还很远。 |

## 当前可用能力

- Python 包骨架与 CLI 存在：`xa-guard` / `xa-bench` entry points 已配置。
- 6 个 gate 文件都有实现，不是完全空目录。
- `Pipeline` 能串起 gate1 → gate2 → gate4(in) → gate3 → gate5 → executor → gate4(out) → gate6。
- stdio 上游 MCP server 与 stdio 下游 MCP client 已有 smoke 测试。
- demo target 和 3 个演示脚本存在，可用于展示间接注入、数据外泄、HITL fallback。
- 评测工具能跑 30 条 seed case，并写出 `bench/.log/last_results.json`、`last_report.json`、`report.html`。
- 前端是离线审计时间线，不是完整管理后台，但可以做演示素材。

## 主要空壳 / 占位清单

1. **SDK 是空的**：`sdk/decorators.py` 的 `@protect` 只透传原函数，没有 mini-pipeline、LangChain callback、Guard session。
2. **AIBOM 是空的**：`scanner.py` 留 TODO，`rater.py` 固定 stub 结果；方向 3 现在只有故事线，没有真实能力。
3. **MCP elicitation 未接入**：`proxy/upstream.py` 留 TODO；关卡 2 现在只能返回 REQUIRE_APPROVAL 或 fallback，不会真的在客户端弹审批窗。
4. **Streamable HTTP 未实现**：上游 `run_streamable_http()` 直接 `NotImplementedError`；下游也只支持 stdio。
5. **OPA / Rego 未实现**：`gate3_policy.py` 的 `backend=rego` 会抛 `NotImplementedError`；当前是受限 Python predicate。
6. **Docker / gVisor 未执行**：`gate5_sandbox.py` 只给 `sandbox_mode`，没有实际把工具调用放进容器。
7. **国密证据链不完整**：SM3/SM2 依赖 gmssl fallback；没有 TSA；签名也不是正式 SM2 私钥流程。
8. **CoT 忠实度未实做**：审计字段里有 `faithfulness_score=1.0`，但没有解释性/忠实度检测算法。
9. **评测规模不足**：当前 30 条 seed，PRD Must 是 290 条 CSAB-Gov-mini；国标完整题库要求更高，只能声明 PoC。
10. **Protocol PDF / 技术方案 / 演示视频未交付**：代码仓库有 docs，但比赛必交的 30 页技术方案 PDF、10 分钟视频、报名表不在仓库内完成。

## 最新验证结果

本次维护时重新执行：

- `PYTHONPATH=src python -m pytest -q`：通过，输出为 93 个测试点全绿（进度显示 77% + 100%）。
- `PYTHONPATH=src python -m bench.cli run --suite bench/cases/csab-gov-mini-seed.yaml --config configs/xa-guard.yaml`：可运行，但最新结果低于 README 旧数字。
- `PYTHONPATH=src python scripts/verify_audit.py --path logs/audit/audit.jsonl`：失败，661 条记录中 34 个 hash_prev 链错误，0 条缺字段。

最新 bench 指标：

| 指标 | 最新值 | 说明 |
|---|---:|---|
| total | 30 | 仍是 seed，不是 PRD 290 用例 |
| pass_rate | 66.67% | 低于 README 之前写的 73.3%，也低于 demo 目标 70% |
| ASR | 22.73% | demo 目标 ≤30%，但离 PRD 中等档 ≤10% 还有明显距离 |
| Recall | 77.27% | seed 上达到 demo 级别，但未达 PRD 90% |
| FPR | 12.5% | 高于 README/demo 目标 ≤5%，需要重点排查 data_safety 误拒 |
| CuP | 87.5% | seed 上尚可，但 data_safety 子项 CuP 为 0 |
| Latency P50 / P95 | 1.80 ms / 2.42 ms | 当前是规则与本地 pipeline，不能代表模型推理/沙箱后的性能 |
| audit_completeness | 100% | bench 统计完整，但独立验链脚本发现历史日志链错误 |

## 距离 PRD 目标的差距

PRD 默认目标是“进取 + 冲刺”，代码交付目标是 L3 政企原型。当前更接近 L1/L2 之间：

- L1 基础：部分满足。6 关卡核心代码可跑，测试存在，但多个关卡仍是规则/fallback/路由决策。
- L2 工程：部分满足。README、测试、bench、demo 都有；但 coverage 数字未跑，README 指标需要同步最新实测。
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

1. 先修 **bench 退化与误报**：对比 `bench/.log/last_results.json`，找出 pass_rate 66.67%、FPR 12.5%、data_safety CuP 0 的具体 case，避免 README 和真实评测继续分裂。
2. 修 **审计验链失败**：定位 `logs/audit/audit.jsonl` 第 401 行附近开始的 hash_prev mismatch；确认是历史日志混用、签名 patch 改写、还是 ChainStore 计算口径问题。
3. 补 **方向 3 AIBOM 最小可用闭环**：至少实现 Python/JSON/YAML 插件扫描、危险 import/网络/文件权限检测、评级解释，并让 supply_chain seed 不再 25%。
4. 补 **关卡 2 真实 HITL 设计**：先以支持 elicitation 的客户端做实测，国产客户端仍按事实源写 fallback，不夸大。
5. 扩 **Policy DSL 到 30 条**：围绕等保 2.0、GB/T 45654 31 类生成内容切片、17 类拒答切片补规则和单测。
6. 扩 **CSAB-Gov-mini 到 290 条**：现在 30 条只能支撑 demo，不能支撑 PRD/答辩指标。
7. 同步文档数字：README 中的 bench 数字、审计字段“14/16”口径、已知不全表需要在下一轮按最新实测更新。
