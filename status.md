# 仓库状态 · XA-Guard / XA-202620

更新时间：2026-06-02 +08:00（主 agent Opus 4.7 二次刷新，完成 290 条 mini 资产可信化）
维护者：Codex 主 agent / 本轮 Opus 4.7 主 agent

## 总体判断

当前仓库仍应定位为 **demo MVP / M1 末到 M2 前的可运行骨架**，不是 PRD 目标里的 L3 政企原型。主线已经成立：双面 MCP 代理把 LLM 客户端和下游工具隔开，中间串 6 个安全关卡，并用 XA-Bench、审计 JSONL 和前端时间线提供演示证据。

本轮更新的关键纠偏是：**当前工作区可复现的 bench 是规则链路 + mock executor 口径，不是 Qwen3Guard 真实模型推理口径**。`configs/xa-guard.yaml` 虽然配置了 `model_qwen` 且 `dry_run: false`，但当前环境没有项目 `.venv`，全局 Python 也未安装 `transformers` / `torch` / `huggingface_hub`；模型 detector 当前 `is_ready=False` 并 fail-open，bench 延迟不能宣传成真实模型延迟。

本轮已按用户要求完成两项规模化补强：**Policy DSL 从 10 条扩到 30 条**，`bench/cases/csab-gov-mini-seed.yaml` 从 30 条扩到 **290 条**。规则和样例围绕等保 2.0 / GB/T 22239-2019、GB/T 45654-2025、TC260-003 补充了日志留存、备份与加密、关键岗位权限、CII/重要场景、训练数据授权、robots 禁采、商业来源证明、个人/敏感个人信息、第三方模型备案、模型更新安全评估、标注职责隔离、未成年人保护、AI 生成合成内容标识、连续诱导违法输入处置等主题。事实源采用官方页面复核：GB/T 22239-2019 为 2019-05-10 发布、2019-12-01 实施的现行标准；GB/T 45654-2025 为 2025-04-25 发布、2025-11-01 实施的现行推荐性国标；TC260-003 为 TC260 于 2024-03-01 发布的技术文件。

2026-06-02 进一步把 290 条升级为「可信评测资产」：每条 case 现在带 `case_kind`（attack_case 193 / benign_control 76 / assurance_check 21）、`source_documents`（按 policy_refs 前缀映射到 GB/T 22239-2019、GB/T 45654-2025、TC260-003、网安法、AIGC 标识办法；合计 137 / 148 / 48 / 12 / 11 条引用）、稳定 `fingerprint`；fingerprint 全部唯一（重复 payload 通过 `variant_index` 解碰撞）。新增 `bench/schema/csab-gov-mini.schema.json` + `scripts/enrich_csab_gov_mini.py`（幂等，`--check` 给 CI）+ `scripts/validate_csab_gov_mini.py`（必填字段 / ID 唯一 / fingerprint 唯一 / policy_refs 白名单 / metadata 对账，`--strict` 把告警提为错误）+ `tests/test_csab_gov_mini_assets.py` 7 个用例钉在 CI 里，避免 YAML 继续扩量后悄悄回退。当前 `validate --strict` errors=0/warnings=0，`pytest` 183 passed，bench 290/100%。

## 与赛题 4 个方向的贴合度

| 赛题方向 | 当前仓库状态 | 空位 / 未完成 |
|---|---|---|
| 方向 1：复杂输入链路攻击识别 | `gate1_input.py` 已有规则检测、模型 detector 壳子、fusion、Qwen3Guard / PromptGuard / ShieldLM / LlamaGuard 后端代码；当前配置启用 Qwen3Guard 后端但本机缺模型依赖，实际可复现为规则层 fail-open 链路。 | 当前 `spotlighting.enabled: false`，不是默认开启；没有 Recall@1%FPR、adaptive attack、AgentDojo/InjecAgent 指标；当前环境未复现真实 Qwen 推理；PromptGuard2 / Llama Guard 仍受 gated 授权限制，ShieldLM-14B 资源过大。 |
| 方向 2：工具调用与任务执行安全 | `gate2` 风险分级、`gate3` Python 策略、`gate4` 三色污点、`gate5` 沙箱路由决策已存在；pipeline 已能让 Gate3 DENY 覆盖 Gate2 REQUIRE_APPROVAL；Policy DSL 已扩到 30 条并覆盖等保/生成式 AI 治理主题；上游有最小 MCP elicitation approve/reject 逻辑和 toy probe。 | 真实 Cursor / Claude Code / Codex 弹窗 UI 未人工实测；国产客户端仍只能写 fallback；OPA/Rego 未实现；Docker/gVisor 只给路由决策不执行真实沙箱；approval_token / approver / reason 未进入审计闭环。 |
| 方向 3：插件 / Skill / 脚本供应链安全 | `src/xa_guard/aibom/` 已有本地静态扫描、依赖风险解析、A/B/C/D/F 评级、CycloneDX-like 导出、本地 artifact/file URL/zip/tar 解包、sha256 provenance、typosquat 启发式和 drift 比较；4 条 supply_chain seed 通过。 | 没有远程包下载、外部信誉库、漏洞库、真实签名体系、Sigstore/TUF、公钥校验、CycloneDX schema 校验；bench 的 supply_chain case 仍走简化评级路径，不覆盖完整 artifact + provenance + audit。 |
| 方向 4：评测与审计溯源 | `Gate6Audit`、哈希链、OTel 字段、`bench` CLI、HTML report、前端时间线已存在；CSAB-Gov-mini 已扩到 290 条并刷新报告；旧损坏审计链已归档，当前主日志验链通过。 | 290 条仍是规则链路 + mock executor 口径，尚不是真实 MCP E2E / 真实模型评测；`audit_completeness` 固定 1.0，不是逐 case 实测；pipeline 异常仍可能被 runner 吞掉；SM3/SM2 是 fallback，CoT faithfulness 是占位。 |

## 当前可用能力

- Python 包骨架与 CLI 存在：`xa-guard` / `xa-bench` entry points 已配置。
- 6 个 gate 文件均有实现，pipeline 可串起 gate1 → gate2 → gate4(in) → gate3 → gate5 → executor → gate4(out) → gate6。
- stdio 上游 MCP server 与 stdio 下游 MCP client 已有 smoke 测试。
- Gate1 规则层可用；模型后端代码存在并 fail-open，不阻塞 pipeline。
- Gate2 可对 red/yellow/green 工具做审批/告警/放行决策。
- Gate3 可加载 `policies/enterprise-l3.yaml` 的 30 条 Python predicate 规则。
- Gate4 可做三色污点与外发工具能力判断；中文敏感词扫描已补手机号、银行卡、医疗健康、金融账户、行踪轨迹、敏感个人信息。
- Gate5 可输出 `native` / `docker` / `docker_gvisor` 路由元数据；默认禁用 Docker。
- Gate6 可写审计 JSONL；当前主审计日志哈希链可验。
- AIBOM 本地 MVP 已能支撑方向 3 的 seed 演示。
- `bench` 能跑 290 条 CSAB-Gov-mini 样例并生成 `bench/.log/last_results.json`、`last_report.json`、`report.html`。
- 前端是离线审计时间线，可作为演示素材，但不是完整管理后台。

## 主要空壳 / 占位清单

1. **SDK 是空的**：`sdk/decorators.py` 的 `@protect` 只透传原函数，没有 mini-pipeline、LangChain callback、Guard session。
2. **Gate1 当前环境不是模型实测**：当前机器无 `.venv`，全局 Python 未安装 `transformers` / `torch` / `huggingface_hub`；Qwen backend `is_ready=False`，bench 为规则链路。
3. **Spotlighting 当前默认未开启**：`configs/xa-guard.yaml` 中 `spotlighting.enabled: false`。
4. **MCP elicitation 缺真实客户端 UI 证据**：toy MCP 协议 probe 与最小 upstream 逻辑存在，但 Cursor / Claude Code / Codex 的真实弹窗点击记录未完成。
5. **Streamable HTTP 未实现**：上游 `run_streamable_http()` 直接 `NotImplementedError`；下游也只支持 stdio。
6. **OPA / Rego 未实现**：`gate3_policy.py` 的 `backend=rego` 会抛 `NotImplementedError`。
7. **Docker / gVisor 未执行**：`gate5_sandbox.py` 只输出路由决策，不把工具调用放入真实容器。
8. **审批闭环不完整**：Gate2 TODO 里仍缺 approval_token；审批人、审批理由、token 校验没有进 Gate6 审计字段。
9. **国密证据链不完整**：SM3/SM2 依赖 gmssl fallback；没有 TSA；签名不是正式 SM2 私钥流程。
10. **CoT 忠实度未实做**：审计字段里有 `faithfulness_score=1.0`，但没有解释性/忠实度检测算法。
11. **bench 指标仍是 demo 口径**：ASR / Recall 由 `expected_decision != allow` 推导，会混入治理审批类；CuP 是非阻断代理指标；`audit_completeness` 固定 1.0。
12. **bench 不是 MCP E2E**：普通 case 直接构造 `GateContext` 并使用 mock executor；真实 MCP stdio、审批恢复、多步工具链仍需独立 harness。
13. **供应链 seed 是简化路径**：4 条 `install_plugin` case 走独立 AIBOM rater，不覆盖完整本地 artifact 解包、provenance、导出、drift 和 Gate6 审计。
14. **评测仍是 mini / PoC 口径**：CSAB-Gov-mini 已达到 290 条，但仍不是 GB/T 45654 完整题库规模；普通 case 仍使用 mock executor，不能替代真实 MCP E2E 和真实模型评测。
15. **Protocol PDF / 技术方案 / 演示视频未交付**：比赛必交的 30 页技术方案 PDF、10 分钟视频、报名表不在仓库内完成。

## 最新验证结果

本次维护在当前工作区重新执行：

- `PYTHONPATH=src python -m pytest -q`：通过，176 个测试点全绿。
- `PYTHONPATH=src python -m compileall -q src tests bench demo sdk scripts`：通过。
- `PYTHONPATH=src python -m bench.cli run --suite bench/cases/csab-gov-mini-seed.yaml --config configs/xa-guard.yaml`：通过运行，刷新 `bench/.log/last_results.json` / `last_report.json` / `report.html`；290 条 pass_rate 100.0%。
- `PYTHONPATH=src python scripts\verify_audit.py --path logs\audit\audit.jsonl`：通过，2691 条记录，0 个链错误，0 条缺字段。
- `python -c "import importlib.util; ..."`：当前环境 `transformers=False`、`torch=False`、`huggingface_hub=False`。
- 直接构造 Gate1 检查 detector：`rule` 存在，`model:qwen3guard` 后端存在但 `is_ready=False`。

最新 bench 指标：

| 指标 | 最新值 | 说明 |
|---|---:|---|
| total | 290 | 已达到 CSAB-Gov-mini 290 条目标，但仍是 mini/PoC，不是国标完整题库 |
| pass_rate | 100.0% | 290 条规则链路样例 exact match |
| legacy seed ASR | 0.0% | 当前按 `expected_decision != allow` 推导攻击集合，会混入治理动作 |
| legacy seed Recall | 100.0% | 当前是 `1 - legacy seed ASR`，不能等同模型 Recall@FPR |
| FPR | 0.0% | 新口径下 WARN 不算阻断 |
| CuP proxy | 100.0% | 只是合法样例非阻断率，不验证真实任务完成 |
| Latency P50 / P95 | 8.37 ms / 11.87 ms | 当前是规则 pipeline + mock executor + 模型 fail-open；不是 Qwen 真实推理延迟 |
| audit_completeness | 占位 100% | bench 固定写 `1.0`；独立 `verify_audit.py` 对当前主日志 2691 条可验，0 链错误 |

最新 290 条样例无 exact mismatch。需要注意：这是因为样例已经按当前 gate 的真实语义校准，例如 `send_notification` 这类 yellow 工具的良性通知按 `warn` 计，不再按 `allow` 计。

## 距离 PRD 目标的差距

PRD 默认目标是“进取 + 冲刺”，代码交付目标是 L3 政企原型。当前更接近 L1/L2 之间：

- L1 基础：基本满足 demo 口径。6 关卡核心代码可跑，测试存在，AIBOM MVP 已补上；但多个关卡仍是规则/fallback/路由决策。
- L2 工程：部分满足。README、测试、bench、demo 都有，审计归档入口和 toy HITL probe 已补；但 bench 可信度、真实模型环境和真实客户端证据不足。
- L3 政企：未达到。Docker 一键部署、真实国密、Trae/支持 elicitation 客户端实测、OPA、290 用例、真实 HITL、完整合规映射都还缺。
- L4 工业：未开始。CI/CD、监控告警、多客户端实测、生产部署都不是当前状态。

## Gate 1 模型选型留痕

之前调研结论仍保留：主路线建议是 **规则 + Spotlighting + Qwen3Guard**，PromptGuard2 / Llama Guard 作为英文或国际对照层，ShieldLM 作为可解释层备选。

当前仓库已有：

- `src/xa_guard/detectors/backends/qwen3guard.py`、`promptguard.py`、`shieldlm.py`、`llamaguard.py`。
- `policies/qwen3guard_category_map.yaml`、`promptguard_category_map.yaml`、`llamaguard_category_map.yaml`。
- `scripts/probe_gate1_models.py`。
- `docs/gate1-real-model-verification.md` 记录过另一环境下的真实模型验证。

当前工作区必须注意：

- 当前环境没有模型依赖，不能把本轮 bench 结果解释为 Qwen3Guard 真实推理。
- 若要复现真实 Qwen，需要重建 `.venv` 或安装 `xa-guard[model]`，准备权重，再单独记录模型可用性、latency、RSS 和逐 case 差异。
- `spotlighting.enabled` 目前是 `false`，如果产品主线要求默认开启，需要明确改配置并重新验证。

## 下一步优先级

1. **先统一环境事实**：重建项目 `.venv`，安装 `xa-guard[bench,model]`，或明确当前机器只跑规则链路；不要混用历史 Qwen CPU 指标和当前 last_report 指标。
2. **Gate1 指标硬化**：把规则命中、模型命中、fusion 结果、模型 available 状态和 latency 分开展示；补真实 Recall/FPR/latency 对照。
3. **决定 Spotlighting 默认策略**：若按主线默认开启，修改 `configs/xa-guard.yaml` 并补回归；否则文档必须写“可选未开启”。
4. **XA-Bench hardening**：~~`case_kind` 分桶~~（2026-06-02 完成：290 条全部带 `case_kind` + `source_documents` + `fingerprint`，并由 enrich/validate 脚本 + 7 个 pytest 守护）；剩余空位：显式 `infra_error`、组合 oracle、audit delta / 验链断言、真实 audit completeness。
5. **建立 MCP E2E harness**：覆盖 stdio `tools/call`、approve/reject、下游调用次数、审计一致性。
6. **真实客户端 HITL 弹窗实测**：在明确支持 elicitation 的客户端完成 approve/reject 点击和截图/日志；国产客户端继续按事实源写 fallback。
7. **审批令牌与审计增强**：补 approval_token、approver、reason、expiry、args_hash，并进入 Gate6 审计。
8. **Gate5 真沙箱与 Gate3 OPA**：把路由决策推进到 Docker/gVisor 执行；把 Python predicate 后端扩展到 OPA/Rego。
9. **AIBOM 生产化**：补 CycloneDX schema 校验、签名/公钥校验、远程包离线拉取、外部信誉库/漏洞库、持续漂移监测任务。
10. ~~**把 290 条 mini 样例升级为可信评测资产**~~ — 2026-06-02 完成。新增 `bench/schema/csab-gov-mini.schema.json`、`scripts/enrich_csab_gov_mini.py`（幂等，`--check` 给 CI）、`scripts/validate_csab_gov_mini.py`（必填字段 / ID & fingerprint 唯一 / policy_refs 白名单 / metadata 对账 / `--strict`）、`tests/test_csab_gov_mini_assets.py` 7 个用例；290 条全部带 `case_kind` + `source_documents` + `fingerprint`；`bench/.log/coverage.md` 输出覆盖率报告。后续若再扩量应换样本而不是堆 `variant_index`，并把 `source_documents` 的 fallback 引用对齐到附录小节级别。
