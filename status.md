# 仓库状态 · XA-Guard / XA-202620

> 本文件描述**当前仓库状态**（差什么、需要改什么、距 PRD 还有多远），不是工作日志。
> 工作流水记 `log.md`，模块流水记各模块 `.log/worklog.md`。
> 快照时间：2026-06-05 +08:00（维护：Claude 主 agent，承接 Codex 主 agent 的策略重构）

---

## 一句话定位

可运行的 **demo MVP / M1 末到 M2 前骨架**，不是 PRD 的 L3 政企原型。主线已成立：双面 MCP 代理把 LLM 客户端与下游工具隔开，中间串 6 关卡（Gate1 输入→Gate2 风险分级→Gate4 入向污点→Gate3 国标/企业策略→Gate5 沙箱路由→executor→Gate4 出向污点→Gate6 审计），用 XA-Bench 290 条、审计 JSONL 哈希链和前端时间线提供演示证据。

最近一轮重点是**还工程债**，不是横向扩规则：策略目录分层重构 + risk_level 单一事实源收敛 + fail-closed 兜底 + 覆盖矩阵脚本。

---

## 测试状态

上一轮全量 `PYTHONPATH=src python -m pytest`：**259 passed / 1 skipped / 0 failed**。1 skip 是 `tests/integration/test_sandbox_runner.py`，因当前 shell 未构建/发现 `xa-guard/sandbox:latest` 镜像，属预期跳过，非回归。

2026-06-05 本次 Gate1/Gate3/覆盖矩阵回归：
- `python scripts/generate_tool_gate_coverage_matrix.py --strict --json`：通过，当前 layered-merged 视图为 tools=48 / gate2=48 / gate3_triggers=44 / gate4=48 / bench_only=0 / gate3_no_bench=23。
- `python scripts/validate_gate3_rule_fixtures.py --strict --json`：通过，Gate3 31 条 baseline 规则均有 1 个正例和 1 个反例，errors=0 / warnings=0。
- `python -m pytest -q --basetemp pytest_tmp_targeted -p no:cacheprovider tests\unit\test_config.py tests\test_tool_gate_coverage_matrix.py tests\test_gate3_rule_fixtures_assets.py tests\unit\test_gate3.py -x --tb=short`：通过，54 个测试点。
- `python -m pytest -q --basetemp pytest_tmp_broad -p no:cacheprovider tests\unit\test_gate1.py tests\unit\test_gate1_detectors.py tests\unit\test_gate2.py tests\unit\test_gate3.py tests\unit\test_gate4.py tests\unit\test_layered_policy.py tests\test_tool_gate_coverage_matrix.py tests\test_gate3_rule_fixtures_assets.py tests\test_aibom_bench_supply_chain.py tests\integration\test_bench_smoke.py -x --tb=short`：通过，183 个测试点。
- `python -m pytest -q --basetemp pytest_tmp_full_current -p no:cacheprovider -x --tb=short`：通过；`tests/integration/test_sandbox_runner.py` 因本机缺少 `xa-guard/sandbox:latest` 镜像按预期 skip 1 条。

**已修复的 fail-closed 回归**：上一快照里 `test_proxy_smoke` 与 `test_mcp_e2e` 因 fail-closed 兜底回归失败——Gate4 `_default_cap`（`output=CONFIDENTIAL` + `NETWORK_EXTERNAL`）让任何**未登记工具在 OUTBOUND 必然 DENY**，连良性 `echo` fixture 也被拒。已按"路线 1"修复：在 baseline 给 demo fixture `echo` 登记 Gate2（legacy `gate2_tool_risks.yaml: echo: green`）+ Gate4（`gate4_capabilities.yaml`：`capabilities: []`、`output_taint: PUBLIC`、`risk_level: green`），**保持 fail-closed 不破窗**——仍是"显式登记的工具才放行，未登记一律从严"。

---

## 本轮已还的工程债（status 顶部历史 一档/二档 已清）

历史 status 顶部列过 5 条"扩规则前必须先修的地基裂缝"，当前状态：

| 债务 | 状态 | 落点 |
|---|---|---|
| 一档①：risk_level 无单一事实源 | ✅ 已收敛 | 唯一源归 `gate4_capabilities.yaml`；`layered.py` 新增 `_derive_tool_risks_from_caps()` 从 caps 派生 Gate2 风险；`manifest.yaml` 移除 `tool_risks` 资源条目；`gate2_tool_risks.yaml` 保留但头部标注废弃（仅 legacy 测试兼容） |
| 一档②：fail-open 方向反了 | ✅ 已改 fail-closed | Gate2 未登记工具默认 `GREEN→YELLOW`（可配 `default_risk`）；Gate4 `_default_cap` 改 `input_max=PUBLIC` / `output=CONFIDENTIAL` / `NETWORK_EXTERNAL`，未登记工具入向/出向都从严。**副作用见上方 broken 段** |
| 一档③：Gate4 OUTBOUND 死代码 | ✅ 已清 | `gate4_taint.py` OUTBOUND 现为单一 DENY 路径（机密经外网/通知工具→DENY），删掉了三元两分支都 DENY、`WARN` 永不可达的半成品 |
| 二档④：无覆盖率矩阵 | ✅ 已有脚本 | `scripts/generate_tool_gate_coverage_matrix.py` + `tests/test_tool_gate_coverage_matrix.py`，输出 `bench/.log/tool_gate_coverage.md`，`--strict` 阻断 Gate3 trigger 缺登记 / risk 漂移 / 非法枚举 |
| 二档⑤：规则无逐条正/反例约定 | ✅ 已文档化 | `docs/规则测试样例约定.md`（含阳历/ISO 8601 日期口径） |

**规则正/反例已升级为强约束**：`bench/cases/gate3-rule-fixtures.yaml`、`bench/schema/gate3-rule-fixtures.schema.json`、`scripts/validate_gate3_rule_fixtures.py` 和 `tests/test_gate3_rule_fixtures_assets.py` 已落地；每条 Gate3 baseline 规则必须有正例命中和反例不命中，validator 会真实执行 Gate3。

---

## 策略目录结构（已分层重构）

按"层级为主轴、关卡为命名"重组，旧 `policies/*.yaml` 平铺已废弃：

```
policies/
  baseline/                       # 项目内置国标兜底，运行时只读
    manifest.yaml                 # 资源清单（已移除 tool_risks 条目）
    gate1_input_patterns.yaml
    gate2_tool_risks.yaml         # 头部标注废弃，manifest 不再引用，仅 legacy 测试兼容
    gate3_rules.yaml              # 原 enterprise-l3.yaml，纠正误导命名
    gate4_capabilities.yaml       # risk_level 唯一事实源
    gate4_sensitive_patterns.yaml
    category_maps/{llamaguard,promptguard,qwen3guard}.yaml
  overlay/                        # 企业可写；<tenant_id>/*.yaml；当前仅 _template
```

`LayeredPolicySource` 把 baseline + overlay 合并为单视图给 Gate2/3/4 共享；单调性门控强制 4 类红线（rule.id 不可覆盖、tool_risks 不可弱化、`input_max_taint` 不可放宽、敏感词不可删 baseline），违例整批 overlay 拒绝并保留旧 snapshot。`watchfiles` 监听 overlay 做原子热加载。每次合并出 `bundle_sha` 写入每条 `AuditRecord` 的 `gen_ai.policy.bundle_sha`。生产 `prefer_layered: true`，单测默认 false。

**当前 baseline / layered-merged 规模**（覆盖矩阵实测）：Gate3 规则 31 条 / 44 个唯一 trigger；Gate4 capabilities 48 工具（risk_level 唯一源，含 demo fixture `echo` 与供应链入口 `install_plugin`）；Gate2 layered 派生 48 工具风险；敏感模式 29 条。覆盖矩阵：`total_tools=48`、`missing_gate2=0`、`missing_gate4=0`、`risk_mismatches=0`、`bench_only=0`、`gate3_no_bench=23`。

**法规依据留痕**：新增 `docs/risk_classification_basis.md`，经多轮 web search 收集 5 个权威来源，核心论断 ≥2 来源交叉核验，支撑 risk_level 分级。

---

## 逐关卡状态

- **Gate1 输入**：规则层可用；Qwen3Guard/PromptGuard/ShieldLM/LlamaGuard 后端代码存在并 fail-open。**当前机器无 `.venv`、全局未装 `transformers/torch/huggingface_hub`，模型 detector `is_ready=False`，bench 是规则链路口径，不能宣传为真实模型推理。** `configs/xa-guard.yaml` 已默认开启 `spotlighting.enabled: true`，非 user 来源会加 `<untrusted_source>` 标记。
- **Gate2 风险分级**：red→审批 / yellow→异步通知 WARN / green→放行；未登记默认 YELLOW（fail-closed）。约 80%。
- **Gate3 国标/企业策略**：31 条 Python predicate 规则可加载；`backend=rego` 已是可运行 MVP（`policy/rego.py` 把 DSL 转 Rego module，有 OPA binary 时走 `opa eval`，无 OPA 时 Python fallback 并在 metadata 标 `rego_mode=python_fallback`，`strict_opa=true` 缺 binary 则 fail-fast）。本机已下载 `tools/opa/opa.exe`（OPA 1.17.0/windows-amd64，已 `.gitignore`），真实 `opa eval` smoke 通过（Gate3 legacy policy_file 路径）。约 70%。当前 31 条规则已有正/反例 fixtures 强约束。
- **Gate4 三色污点**：入向/出向污点 + 工具能力边界；未登记工具 fail-closed；中文敏感词覆盖手机号/银行卡/医疗/金融账户/行踪/敏感个人信息。约 75%。
- **Gate5 沙箱**：按风险路由 green→native / yellow→docker / red→docker_gvisor（无 runsc 降级 docker），输出 executor 可消费的结构化沙箱策略字段。`DownstreamRouter` 会按 `sandbox.py` 构造真实 `docker run`（禁网 / 只读 rootfs / `--cap-drop ALL` / no-new-privileges / pids/内存/CPU 限制）。本机 Docker Desktop 真实 smoke 已验证禁网+只读 rootfs 生效（`docker/sandbox.Dockerfile` 非 root uid 10001 + `scripts/build_sandbox_image.sh` 可复现构建）。**默认仍禁用 Docker**，显式开启才进真实路径。gVisor(`runsc`) 未在 Linux 实测；streamable-http 下游未沙箱化。
- **Gate6 审计**：写审计 JSONL 哈希链可验；含 OTel 字段、`bundle_sha`、approval_token/approver/reason/expires_at/args_hash、sandbox mode/enforced/image/runtime。

---

## 与赛题 4 个方向贴合度

| 方向 | 当前状态 | 主要空位 |
|---|---|---|
| 1 复杂输入链路攻击识别 | Gate1 规则 + 4 个模型后端壳 + fusion；配置启用 Qwen3Guard 但本机缺依赖，实测为规则层 fail-open；Spotlighting 已默认开启 | 无 Recall@1%FPR / adaptive / AgentDojo / InjecAgent 指标；真实 Qwen 未复现；PromptGuard2/LlamaGuard gated、ShieldLM-14B 资源过大 |
| 2 工具调用与执行安全 | Gate2/3/4/5 链路成立，Gate3 DENY 可覆盖 Gate2 审批；baseline+overlay 双层策略 + 单调性 + 热加载；真 JSON-RPC `tools/call` + elicitation approve/reject + 审批令牌执行闸门由 `test_mcp_e2e.py` 覆盖；Gate3 正/反例 fixtures 已强约束 | 真实客户端弹窗 UI 未实测；overlay merge 跨资源强校验仍有限；layered/hot-reload 合并视图仍走 Python predicate（未接 Rego） |
| 3 插件/Skill/脚本供应链 | `aibom/` 本地静态扫描 + 依赖风险 + A-F 评级 + CycloneDX **1.6** 导出 + artifact 解包 + sha256 provenance + typosquat + drift；**已生产化 5 项**：CycloneDX schema 校验（`schema_validator.py`，jsonschema+内建 fallback）、BOM 签名/公钥验签（`signing.py`，Ed25519 真实非对称 / SM2 降级 / HMAC + trust store）、远程包离线拉取（`offline_fetch.py`，严格离线 fail-closed 缓存）、外部信誉/漏洞库（`intel.py`+`data/vulndb.json` 10 CVE 种子 +`reputation.json`，PEP440 区间匹配）、持续漂移监测（`drift_monitor.py`，持久化快照+JSONL 账本+严重度分级）；`gateway.admit()` 总装为准入流水线，`xa-aibom` CLI 暴露；新增约 128 条单测全绿；25 条 supply_chain bench 仍通过；`install_plugin` 已纳入 Gate3/Gate4 与 layered Gate2 派生总账 | 漏洞/信誉库为**离线种子快照**（非实时 feed、非 OSV 全量同步）；无 Sigstore/TUF（自管 trust store + Ed25519）；SM2 仍 gmssl 缺失下 HMAC 降级；供应链 **bench 仍走旧 `rate_install_request` 简化口径未接 gateway**（接入会翻 SCM-003 基线，需重新 fingerprint）；真实 MCP 安装链路（gate 级）尚未路由到 gateway |
| 4 评测与审计溯源 | Gate6 哈希链 + OTel + bench CLI + HTML report + 前端时间线；CSAB-Gov-mini 290 条；主审计日志验链通过 | 290 条仍是规则链路+mock executor 口径，非真实 MCP E2E / 真实模型评测；`audit_completeness` 固定 1.0；SM3/SM2 是 gmssl fallback；CoT faithfulness 是占位 |

---

## 主要空壳 / 占位清单

1. **SDK 空**：`sdk/decorators.py` 的 `@protect` 只透传，无 mini-pipeline / LangChain callback。
2. **Gate1 非模型实测**：本机无模型依赖，bench 为规则链路。
3. **真实 Spotlighting 效果指标未量化**：默认已开启，但尚未给出 AgentDojo/InjecAgent 或自适应间接注入集上的对照指标。
4. **MCP elicitation 缺真实客户端 UI 证据**：toy probe + 最小 upstream 逻辑在，Cursor/Claude Code/Codex 真实弹窗点击记录未做。
5. **Streamable HTTP 未实现**：上游 `run_streamable_http()` 抛 `NotImplementedError`，下游仅 stdio。
6. **OPA/Rego**：Gate3 backend MVP 已落地（含本机真实 `opa eval` smoke）；剩 layered/hot-reload 合并视图接 Rego、复杂 DSL 转译扩展。
7. **gVisor 未实测**：Docker 真沙箱已验证，runsc 未在 Linux 实测；streamable-http 下游未沙箱化。
8. **审批令牌**：HMAC-SHA256 签发/验签 + `run_after_approval` 执行前验签做执行闸门已落地；剩审批人强认证、HMAC→SM2/RSA 非对称、verify_audit 跨记录一致性。
9. **国密证据链不完整**：SM3/SM2 走 gmssl fallback，无 TSA，非正式 SM2 私钥流程。
10. **CoT 忠实度未实做**：`faithfulness_score=1.0` 是占位。
11. **bench 指标 demo 口径**：ASR/Recall 由 `expected_decision != allow` 推导会混入治理审批类；`audit_completeness` 固定 1.0。
12. **bench 非 MCP E2E**：普通 case 直接造 `GateContext` + mock executor。
13. **供应链 seed 简化路径**：`install_plugin` 已进入统一工具总账，AIBOM 生产化 5 项已落地（见方向 3 行），但 bench case 仍走独立 `rate_install_request` 简化口径，未接 `gateway.admit()`（接入会因漏洞库命中翻转 SCM-003 等基线，需重新 fingerprint）。
14. **评测 mini/PoC 口径**：290 条非 GB/T 45654 完整题库规模。
15. **Protocol PDF / 技术方案 / 演示视频未交付**：30 页方案、10 分钟视频、报名表不在仓库内。

---

## 最新 bench 指标（规则链路 + mock executor 口径）

| 指标 | 值 | 说明 |
|---|---:|---|
| total | 290 | CSAB-Gov-mini，mini/PoC 非国标完整题库 |
| pass_rate | 100.0% | exact match |
| ASR | 0.0% | `expected_decision != allow` 推导，混入治理动作 |
| Recall | 100.0% | `1 - ASR`，非模型 Recall@FPR |
| FPR | 0.0% | WARN 不算阻断 |
| CuP proxy | 100.0% | 仅良性非阻断率 |
| Latency P50/P95 | 54.25 / 85.59 ms | 规则 pipeline + mock executor + 模型 fail-open，非 Qwen 真实延迟 |
| audit_completeness | 1.0（占位） | bench 固定写 1.0；独立 `verify_audit.py` 对主日志验链 0 错误 |

> 注意：bench 290 条用的是已登记工具，与上方 `echo` fixture 登记修复无关；指标仍是规则链路口径，不能等同真实模型评测。

---

## 距 PRD 目标差距

PRD 默认"进取+冲刺"，代码目标 L3 政企原型，当前在 L1/L2 之间：

- **L1 基础**：基本满足 demo 口径，6 关卡可跑、测试存在、AIBOM MVP 在；多关卡仍是规则/fallback/路由决策。
- **L2 工程**：部分满足。README/测试/bench/demo/审计归档/审批闭环/覆盖矩阵在；本次定向回归已覆盖 Spotlighting 默认配置、Gate3 fixtures 强约束、layered-merged 覆盖矩阵与 `install_plugin` 总账口径。bench 可信度、真实模型环境、真实客户端证据仍不足。
- **L3 政企**：未达到。一键部署、真实国密、支持 elicitation 客户端实测、layered 接 OPA、真实 HITL、完整合规映射仍缺。
- **L4 工业**：未开始。

---

## 下一步优先级

1. **统一环境事实**：重建 `.venv` 装 `xa-guard[bench,model]`，或明确只跑规则链路；不混用历史 Qwen CPU 指标与当前 last_report。
2. **Gate1 指标硬化**：规则命中 / 模型命中 / fusion / 模型 available / latency 分开展示，补真实 Recall/FPR/latency 对照。
3. **Spotlighting 效果评测**：默认已开启，下一步补开启/关闭对照指标和间接注入样例集证据。
4. **真实客户端 HITL 弹窗实测**：在支持 elicitation 的客户端完成 approve/reject 点击与截图/日志。
5. **Gate5 gVisor / Gate3 layered 接 OPA**：Linux+runsc 验证 gVisor、沙箱接真实 MCP E2E；把 layered/hot-reload 合并视图切到 Rego engine。
6. **AIBOM 生产化**：✅ 5 项已落地（CycloneDX 1.6 schema 校验 / Ed25519 签名验签 / 远程包离线拉取 / 离线漏洞+信誉库 / 持续漂移监测，`gateway.admit()`+`xa-aibom` CLI）。剩余：把 supply_chain bench 与真实 MCP 安装链路接到 gateway（需重新生成 SCM seed fingerprint 与重判预期）；漏洞/信誉库改为可定期同步的 feed；SM2 真实私钥路径。
7. **交付物**：30 页技术方案 PDF、10 分钟视频、报名表。
