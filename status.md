# 仓库状态 · XA-Guard / XA-202620

> 本文件描述**当前仓库状态**（差什么、需要改什么、距 PRD 还有多远），不是工作日志。
> 工作流水记 `log.md`；L2 冻结清单见 `docs/L2-acceptance-checklist.md`；验证命令见 `docs/L2-verification-commands.md`。
> 快照时间：2026-06-18 09:40 +08:00

---

## 一句话定位

**L2 工程完成（Hard + Competition-trusted 口径）**：6 关卡 pipeline 可跑、**覆盖率 82%**（≥50% L2 Hard）、290 条 XA-Bench、Gate1-only evaluator、覆盖矩阵、Gate3 fixtures、Gate5 Docker sandbox smoke、审计验链。bench 已改为全样本审计分母，infra error 不再混入安全指标，290 条最新运行均有唯一 trace/record hash 且可离线复算。L3 政企原型已多 git checkpoint（本地 9 个，未 push）：Docker Compose、Streamable HTTP 上游、docker profile 静态工具发现、HITL pending approval fallback + **真实 `opencode run` 端到端闭环证据（trace `2eed0319`，`require_approval → allow`，approver ops-lead，审计链 2 records 0 errors，详见 `docs/evidence/l3-hitl-pending-approval-2026-06-18.md`）**、bench supply_chain 与真实 MCP `install_plugin` 离线 preflight 接 AIBOM gateway、可复现性能基准、SDK/LangChain Tool preflight、本地文件 TSA anchor、外部 benchmark adapter skeleton、OPA merged-view 导出、**`opencode run` 真实 LLM→MCP→AIBOM F 级 deny 端到端实测证据**、**真实 SM3 国密哈希链（GB/T 32905-2016，纯 Python 无依赖，不再降级 SHA-256）**、**Docker 一键部署 runtime 已验收（`docker compose build/up` 实跑，容器 healthy，`/healthz` 200，部署 verifier 6/6 pass）**、**真实 SM2 签名（GB/T 32918）+ TSA 时间戳证据（SM2-with-SM3 token，可嵌入公钥自验，证据 `docs/evidence/l3-sm2-tsa-evidence-2026-06-18.json`）**；PRD L3 三要件（Docker 一键部署 / 国密支持 / 性能基准）**均已闭合**；但 **PRD L3 仍未整体达成**（AgentDojo/InjecAgent 官方复现、gVisor Linux、500+ 题库、完整 LangChain wrapper、faithfulness 算法仍缺）。

---

## L2 工程完成（客观陈述）

| 维度 | 状态 | 证据 |
|---|---|---|
| **Hard L2（PRD §4.2）** | ✅ | LOC ≈ 7900+（src+bench）；README 已对齐当前策略目录与命令；`pytest --cov` **82%**；6 关单元测试齐全 |
| **全量 pytest** | ✅ 代码回归通过 | 历史 L2 证据为 394 passed / 0 skipped；本轮当前环境 Docker daemon/本地 sandbox 镜像不可用，全量回归通过但 `test_sandbox_runner.py` 1 skip |
| **XA-Bench 290** | ✅ | `python -m bench.cli run …` → pass_rate 100%，`audit_completeness=1.0`（265 条走 pipeline 写审计） |
| **Gate1-only evaluator** | ✅ | `python scripts/evaluate_gate1.py --detectors rule`；Gate1-scope 60 attack：Recall **68.33%**，FPR blocking **0**；含 `recall_at_fpr` |
| **覆盖矩阵** | ✅ | `--strict`：tools=48 / gate2=48 / gate4=48 / bench_only=0 |
| **Gate3 fixtures** | ✅ | 31 规则 × 正/反例，`validate_gate3_rule_fixtures.py --strict` errors=0 |
| **审计完整率** | ✅ 已实测 | `bench/metrics.py` 聚合 Gate6 `audit_completeness`；非固定占位 |
| **Bench 证据可信度** | ✅ 全样本闭环 | 缺审计按 0 进入总分母；infra error 单列且不进入 ASR/FPR/CuP；CLI 对 infra/缺审计/不完整审计非 0；`last_results.json` 保留 trace、record hash、审计与错误字段，可离线复算同一报告 |
| **Gate5 沙箱镜像** | 🟡 代码与历史证据可用，当前环境待恢复 | 历史已在本机构建 `xa-guard/sandbox:latest` 并通过真实沙箱测试；本轮 Docker Desktop daemon 未启动，本地镜像不可用导致集成测试 skip |
| **L3 部署入口** | ✅ runtime 已验收 | `docker-compose.yml` + Dockerfiles + `configs/xa-guard.docker.yaml`；本机 Docker Desktop 29.5.2 实跑 `docker compose build sandbox-image` + `up --build -d xa-guard`，容器 `Up (healthy)`，`/healthz` 返回 `{"status":"ok","transport":"streamable-http"}`；`scripts/verify_l3_deployment.py --run-build --run-up` 6/6 steps pass，证据 `docs/evidence/l3-deployment-verification.json`；docker profile 使用静态 downstream manifest；host 端口用 13000:3000 规避 Windows 保留端口 2924–3023，探 healthz 需 `NO_PROXY=127.0.0.1,localhost` |
| **L3 性能基准** | ✅ 本地规则链证据 | `scripts/benchmark_l3_performance.py` 测真实六关卡 + Gate6 落盘；500 请求/并发 10 实测 P50 20.305ms、P95 168.273ms、53.486 QPS、峰值 RSS 62.996MB，达到 PRD 中等档；范围不含 MCP 传输、模型推理、真实工具和多机压测 |
| **L3 供应链准入** | 🟡 原型 | bench supply_chain 与真实 MCP `tools/call install_plugin` 均走 AIBOM gateway；本地目录/归档和 hash 可扫描，服务端离线缓存命中的远程引用可扫描，未镜像远程引用 fail-closed；仍非真实 marketplace/IDE 安装器 |
| **L3 SDK 非透传** | 🟡 原型 | `xa_guard.protect` / `xa_guard.sdk.protect` 已在调用原函数前跑 pipeline preflight；`xa_guard.integrations.langchain.protect_tool()` 支持单个 BaseTool 强阻断 wrapper；当前环境未安装 langchain-core，集成测试 skip |
| **L3 审计锚定** | 🟡 原型 | `scripts/anchor_audit.py` 生成本地文件 TSA anchor；manifest 覆盖 audit 文件 SHA-256、字节数、记录数、首尾 record_hash，并写 `anchors/index.jsonl` 串联；这不是外部可信 TSA |
| **L3 外部 benchmark** | 🟡 证据包原型 | `bench.external` 可离线 normalize/validate/smoke-metrics/archive AgentDojo/InjecAgent 用户导出文件；archive 生成 normalized、validation、smoke metrics、report、manifest 和 README，记录 input/normalized/schema hash；`--run-projection` 可把 normalized projection payload 跑本地 XA-Guard pipeline 并生成隔离 audit + audit-verify；强制 `official_claim=false`；不运行官方环境、不产生官方成绩 |
| **L3 OPA/Rego** | 🟡 原型 | `Gate3 backend=rego + prefer_layered` 可使用 LayeredPolicySource merged rules；`scripts/export_opa_policy.py` 可导出 OPA `data.json` + `gate3.rego` + manifest；真实 OPA CLI 运行视本机 binary |
| **L3 HITL fallback** | 🟡 原型 → ✅ `opencode run` 实测闭环 | 上游 MCP 内置 `xa_guard_list_pending_approvals` / `xa_guard_approve_pending`；无 elicitation 客户端会暂存红色工具调用；`pending_approvals_path` / `XA_GUARD_PENDING_APPROVAL_STORE` 可启用本地 JSONL pending ledger，支持单机重启恢复未过期非敏感 pending 项；ledger/list 优先按工具 `inputSchema` 的敏感标注脱敏并字段名回退；**真实 `opencode run` 端到端闭环已验证**：glm-5.2 调用 `pending_approval_op` → Gate2 REQUIRE_APPROVAL → pending staging → `xa_guard_approve_pending(approve=true, approver=ops-lead)` → 下游执行 → 审计链 `require_approval → allow`（2 records, 0 errors, trace `2eed0319`），证据 `docs/evidence/l3-hitl-pending-approval-2026-06-18.md`；真实国产 IDE Trae 弹窗截图仍待补 |

**Competition-trusted L2 当前已闭合**：真实 Qwen GPU 复跑 Gate1、真实 IDE HITL 截图归入 L3/冲刺证据——见 L3 段。

---

## 测试状态

- 历史 L2 闭合：`PYTHONPATH=src python -m pytest -q --basetemp pytest_tmp_full_after_sandbox -p no:cacheprovider -x --tb=short`：**394 passed / 0 skipped / 0 failed**
- 本轮最终全量：`python -m pytest -q --basetemp pytest_tmp_l3_round3_full -p no:cacheprovider -x --tb=short`：通过，**2 skip**（`xa-guard/sandbox:latest` 本地镜像不可用；未安装 `langchain_core`）
- `python -m pytest -q --basetemp pytest_tmp_l3_full -p no:cacheprovider -x --tb=short`：全量通过（进度 100%，无失败）
- `python -m bench.cli run --suite bench/cases/csab-gov-mini-seed.yaml --config configs/xa-guard.yaml`：290 条 pass_rate **1.0**，`audit_completeness=1.0`，P50 **75.14 ms**，P95 **558.4 ms**（P95 尚未达 PRD 中等档 300 ms）
- Gate5 sandbox：历史已构建本机镜像 `xa-guard/sandbox:latest` 并真实执行通过，验证禁网 + 只读 rootfs；本轮当前环境镜像不可用，需启动 Docker Desktop 后重建/重跑
- Streamable HTTP：临时 3099 端口启动 `run_streamable_http()`，`/healthz` 返回 OK；`mcp.client.streamable_http.streamablehttp_client` + `ClientSession.list_tools()` 协议 smoke 通过
- SDK：`python -m pytest -q --basetemp pytest_tmp_l3_sdk -p no:cacheprovider tests\test_sdk_protect.py -x --tb=short`：4 passed
- 本轮 SDK 后全量：`python -m pytest -q --basetemp pytest_tmp_l3_full_sdk -p no:cacheprovider -x --tb=short`：全量通过（进度 100%，无失败）
- 本轮审计锚定：`python -m pytest -q --basetemp pytest_tmp_l3_tsa2 -p no:cacheprovider tests\unit\test_audit_tsa.py tests\unit\test_merkle.py tests\unit\test_audit_archive.py -x --tb=short`：11 passed；CLI smoke 生成 anchor 并通过 `--verify-anchor-index`
- 本轮 Compose/Gate5：`python -m pytest -q --basetemp pytest_tmp_l3_sandbox -p no:cacheprovider tests\unit\test_sandbox_policy.py tests\unit\test_downstream_sandbox.py tests\unit\test_gate5.py -x --tb=short`：13 passed；`docker compose config` 通过
- 本轮 L3 工具发现静态化：`python -m pytest -q --basetemp pytest_tmp_l3_discovery -p no:cacheprovider tests\unit\test_config.py tests\unit\test_gate5.py tests\unit\test_downstream_sandbox.py tests\integration\test_proxy_smoke.py tests\integration\test_l3_compose_config_smoke.py -x --tb=short`：20 passed
- 本轮外部 benchmark adapter：`python -m pytest -q --basetemp pytest_tmp_l3_external -p no:cacheprovider tests\unit\test_external_benchmarks.py ... -x --tb=short`：21 passed；`python -m bench.external.cli normalize/validate/smoke-metrics` smoke 通过
- 本轮外部 benchmark evidence archive：`python -m pytest -q --basetemp pytest_tmp_l3_external_archive -p no:cacheprovider tests\unit\test_external_benchmarks.py -x --tb=short`：5 passed；`archive` 子命令可生成 manifest/report/normalized/validation/smoke-metrics/README，manifest 校验 input/normalized/schema hash 且 `official_claim=false`
- 本轮 external archive 宽回归：`python -m pytest -q --basetemp pytest_tmp_l3_external_archive_broad -p no:cacheprovider tests\unit\test_external_benchmarks.py tests\unit\test_opa_export.py tests\integration\test_l3_compose_config_smoke.py tests\unit\test_downstream_sandbox.py tests\integration\test_mcp_e2e.py tests\test_approval.py -x --tb=short`：27 passed；`python -m compileall -q bench src tests`：通过
- 本轮 external archive projection：`python -m pytest -q --basetemp pytest_tmp_l3_external_projection2 -p no:cacheprovider tests\unit\test_external_benchmarks.py -x --tb=short`：6 passed；`python -m bench.external.cli archive --benchmark agentdojo --input bench/external/fixtures/agentdojo_smoke.jsonl --out-dir pytest_tmp_external_projection_smoke2\agentdojo --run-projection --config configs/xa-guard.yaml`：成功生成 `xa-guard-projection/results.json`、`summary.json`、隔离 `audit/audit.jsonl` 与 `audit-verify.json`
- 本轮 external projection 宽回归：`python -m pytest -q --basetemp pytest_tmp_l3_external_projection_broad -p no:cacheprovider tests\unit\test_external_benchmarks.py tests\unit\test_opa_export.py tests\integration\test_l3_compose_config_smoke.py tests\unit\test_downstream_sandbox.py tests\integration\test_mcp_e2e.py tests\test_approval.py tests\test_pipeline_smoke.py -x --tb=short`：33 passed；`python -m compileall -q bench src tests`：通过
- 本轮综合靶向：`python -m pytest -q --basetemp pytest_tmp_l3_round2_targeted -p no:cacheprovider tests\unit\test_external_benchmarks.py tests\unit\test_config.py tests\unit\test_gate5.py tests\unit\test_downstream_sandbox.py tests\integration\test_l3_compose_config_smoke.py tests\integration\test_proxy_smoke.py tests\integration\test_mcp_e2e.py -x --tb=short`：24 passed
- 本轮 OPA merged-view：`python -m pytest -q --basetemp pytest_tmp_l3_opa -p no:cacheprovider tests\unit\test_opa_export.py tests\unit\test_gate3.py::test_rego_backend_uses_layered_merged_view ... tests\unit\test_layered_policy.py -x --tb=short`：39 passed；`python scripts\export_opa_policy.py --out-dir pytest_tmp_l3_opa_cli\opa-bundle` 导出成功
- 本轮 SDK/LangChain：`python -m pytest -q --basetemp pytest_tmp_l3_opa_sdk -p no:cacheprovider tests\unit\test_opa_export.py tests\unit\test_gate3.py::test_rego_backend_uses_layered_merged_view tests\test_sdk_protect.py tests\test_langchain_integration.py -x --tb=short`：通过，1 skip（未安装 `langchain_core`）
- 本轮 OPA/SDK/adapter/discovery 综合靶向：`python -m pytest -q --basetemp pytest_tmp_l3_round3_targeted -p no:cacheprovider tests\unit\test_opa_export.py tests\unit\test_gate3.py::test_rego_backend_uses_layered_merged_view tests\unit\test_layered_policy.py tests\test_sdk_protect.py tests\test_langchain_integration.py tests\unit\test_external_benchmarks.py tests\integration\test_l3_compose_config_smoke.py tests\unit\test_downstream_sandbox.py -x --tb=short`：通过，1 skip（未安装 `langchain_core`）
- Docker Compose 实际构建：`docker compose build sandbox-image` 未能执行，原因是本机 Docker Desktop daemon 未启动（`dockerDesktopLinuxEngine` pipe 不存在）；完整 `docker compose up --build -d` 仍待验收
- 本轮 HITL pending fallback：`python -m pytest -q --basetemp pytest_tmp_l3_pending -p no:cacheprovider tests\unit\test_upstream_elicitation.py tests\integration\test_mcp_e2e.py -x --tb=short`：10 passed；覆盖无 elicitation 时 pending、list、approve、reject、一次性消费和 `require_approval -> allow` 审计闭环
- 本轮 HITL 综合回归：`python -m pytest -q --basetemp pytest_tmp_l3_pending_policy2 -p no:cacheprovider tests\unit\test_upstream_elicitation.py tests\integration\test_mcp_e2e.py tests\unit\test_gate2.py tests\test_tool_gate_coverage_matrix.py -x --tb=short`：30 passed；`python -m compileall -q src tests`：通过；`python -m pytest -q --basetemp pytest_tmp_l3_pending_broad2 -p no:cacheprovider ... -x --tb=short`：39 passed，1 skip（未安装 `langchain_core`）
- 本轮 HITL 拒绝审计 / token 防重放：`python -m pytest -q --basetemp pytest_tmp_l3_hitl_reject_replay2 -p no:cacheprovider tests\test_approval.py tests\test_pipeline_smoke.py tests\unit\test_upstream_elicitation.py tests\integration\test_mcp_e2e.py -x --tb=short`：27 passed；`python -m compileall -q src tests`：通过；覆盖 reject `require_approval -> deny` 审计、approval token 进程内 one-shot、list/approve/reject operator token 校验
- 本轮 HITL 宽回归：`python -m pytest -q --basetemp pytest_tmp_l3_hitl_broad -p no:cacheprovider tests\test_approval.py tests\test_pipeline_smoke.py tests\unit\test_upstream_elicitation.py tests\integration\test_mcp_e2e.py tests\integration\test_proxy_smoke.py tests\integration\test_l3_compose_config_smoke.py tests\unit\test_config.py tests\unit\test_downstream_sandbox.py tests\unit\test_gate5.py tests\unit\test_opa_export.py tests\unit\test_gate3.py::test_rego_backend_uses_layered_merged_view tests\test_sdk_protect.py tests\test_langchain_integration.py -x --tb=short`：55 passed，1 skip（未安装 `langchain_core`）
- 本轮 L3 部署 verifier：`python -m pytest -q --basetemp pytest_tmp_l3_deploy_verify4 -p no:cacheprovider tests\unit\test_l3_deployment_verifier.py -x --tb=short`：3 passed；`python scripts\verify_l3_deployment.py --output pytest_tmp_l3_deployment_verification4.json`：生成 `xa-l3-deployment-verification/v0.1` 报告，文件/hash、Compose 静态摘要、`docker compose config` 通过，`docker_version` 因 Docker Desktop daemon 未启动标为 `blocked_external_dependency`
- 本轮 L3 部署相关宽回归：`python -m pytest -q --basetemp pytest_tmp_l3_deploy_broad4 -p no:cacheprovider tests\unit\test_l3_deployment_verifier.py tests\integration\test_l3_compose_config_smoke.py tests\unit\test_config.py tests\unit\test_downstream_sandbox.py tests\unit\test_gate5.py tests\integration\test_proxy_smoke.py -x --tb=short`：23 passed；`python -m compileall -q scripts src tests`：通过；`git diff --check`：通过，仅 CRLF 提示
- 本轮 L3 HITL pending ledger：`python -m pytest -q --basetemp pytest_tmp_l3_pending_ledger_e2e1 -p no:cacheprovider tests\unit\test_pending_ledger.py tests\unit\test_upstream_elicitation.py tests\integration\test_mcp_e2e.py -x --tb=short`：17 passed；覆盖 pending ledger 序列化/恢复/过期清理、app 重建后 list/approve/reject、approval token 不落 ledger、`require_approval -> allow` 审计验链
- 本轮 L3 HITL pending ledger 宽回归：`python -m pytest -q --basetemp pytest_tmp_l3_pending_ledger_broad1 -p no:cacheprovider tests\unit\test_pending_ledger.py tests\unit\test_upstream_elicitation.py tests\integration\test_mcp_e2e.py tests\test_approval.py tests\test_pipeline_smoke.py tests\integration\test_proxy_smoke.py tests\unit\test_config.py -x --tb=short`：38 passed；`python -m compileall -q src tests`：通过；`git diff --check`：通过，仅 CRLF 提示
- 本轮 L3 HITL pending ledger 脱敏：`python -m pytest -q --basetemp pytest_tmp_l3_pending_redaction3 -p no:cacheprovider tests\unit\test_pending_ledger.py tests\unit\test_upstream_elicitation.py tests\integration\test_mcp_e2e.py -x --tb=short`：22 passed；覆盖敏感键递归脱敏、pending list 不返回敏感明文、ledger 不落敏感明文、重启后敏感参数 approve fail-closed 并写 `require_approval -> deny`
- 本轮 L3 HITL pending ledger 脱敏宽回归：`python -m pytest -q --basetemp pytest_tmp_l3_pending_redaction_broad1 -p no:cacheprovider tests\unit\test_pending_ledger.py tests\unit\test_upstream_elicitation.py tests\integration\test_mcp_e2e.py tests\test_approval.py tests\test_pipeline_smoke.py tests\integration\test_proxy_smoke.py tests\unit\test_config.py -x --tb=short`：43 passed；`python -m compileall -q src tests`：通过；`git diff --check`：通过，仅 CRLF 提示
- 本轮 L3 HITL pending schema 脱敏：`python -m pytest -q --basetemp pytest_tmp_l3_pending_schema_redaction1 -p no:cacheprovider tests\unit\test_pending_ledger.py tests\unit\test_upstream_elicitation.py tests\integration\test_mcp_e2e.py -x --tb=short`：25 passed；覆盖 `x-xa-guard-sensitive`、`writeOnly`、schema 标注数组/对象、elicitation 文案脱敏、字段名回退
- 本轮 L3 HITL pending schema 脱敏宽回归：`python -m pytest -q --basetemp pytest_tmp_l3_pending_schema_broad1 -p no:cacheprovider tests\unit\test_pending_ledger.py tests\unit\test_upstream_elicitation.py tests\integration\test_mcp_e2e.py tests\test_approval.py tests\test_pipeline_smoke.py tests\integration\test_proxy_smoke.py tests\unit\test_config.py tests\integration\test_l3_compose_config_smoke.py -x --tb=short`：47 passed；`python -m compileall -q src tests`：通过
- 本轮 L3 AIBOM 真实 MCP preflight 定向回归：`python -m pytest -q --basetemp pytest_tmp_l3_aibom_mcp2 -p no:cacheprovider tests\unit\test_aibom_gateway.py tests\unit\test_upstream_elicitation.py tests\integration\test_mcp_e2e.py tests\test_aibom_bench_supply_chain.py -x --tb=short`：31 passed；覆盖本地归档/hash、离线镜像、未镜像远程 fail-closed、恶意安装下游 0 次、干净安装 `require_approval -> allow` 与审计验链
- 本轮 AIBOM/MCP 宽回归：`python -m pytest -q --basetemp pytest_tmp_l3_aibom_mcp3 -p no:cacheprovider tests\unit\test_aibom_gateway.py tests\unit\test_upstream_elicitation.py tests\integration\test_mcp_e2e.py tests\test_aibom_bench_supply_chain.py tests\test_pipeline_smoke.py tests\integration\test_proxy_smoke.py tests\unit\test_config.py -x --tb=short`：41 passed；`python -m compileall -q src tests demo` 与 `git diff --check` 通过（仅 CRLF 提示）
- OpenCode 真实 LLM 客户端 smoke：`configs/opencode.l3-smoke.json` 成功连接 `xa_guard_l3_smoke`；`opencode.cmd run` 实际调用 `xa_guard_l3_smoke_install_plugin`，恶意源码被 `aibom_gateway` 以 F 级拒绝，trace `e4abab76-9b3d-4556-8d08-06be6bcc77ce`；`scripts/verify_audit.py` 验证 `logs/opencode-smoke/audit.jsonl` 2 records、0 chain/hash errors、0 missing-field records
- L3 性能证据：`python scripts\benchmark_l3_performance.py --config configs\xa-guard.opencode-smoke.yaml --requests 500 --warmup 30 --concurrency 10 --output docs\evidence\l3-performance-benchmark-2026-06-18.json --require-targets`：P50 20.305ms、P95 168.273ms、QPS 53.486、峰值 RSS 62.996MB，四项 PRD 中等档 target 全部通过；530 条含 warmup 的 Gate6 审计记录验链通过
- L3 性能宽回归：`python -m pytest -q --basetemp pytest_tmp_l3_perf_broad -p no:cacheprovider tests\unit\test_l3_performance_benchmark.py tests\test_pipeline_smoke.py tests\unit\test_gate6_audit.py tests\unit\test_config.py tests\integration\test_mcp_e2e.py tests\unit\test_aibom_gateway.py -x --tb=short`：37 passed；`compileall`、Ruff、evidence 脚本 hash/targets 校验和 `git diff --check` 通过
- Bench 证据可信度定向回归：`tests/unit/test_bench_runner_evidence.py`、`test_bench_evidence_truth.py`、`test_verify_audit_cli.py`、pipeline/AIBOM/bench/MCP 相关共 27 passed；Ruff 通过
- 290 条权威 CLI 复跑：`total=290`、`evaluated_total=290`、`infra_errors=0`、`audit_missing=0`、`audit_incomplete=0`、`audit_completeness=1.0`、pass rate 1.0；290 个唯一 trace、290 个 record hash，`last_results.json` 离线复算与 `last_report.json` 完全一致；累计 `logs/audit/audit.jsonl` 28,095 records 验链 0 错误
- Bench/Pipeline 可信口径改动后全量 pytest 100% 通过；2 skip 分别为当前环境未安装 `langchain_core` 与本机缺少 Docker sandbox 镜像，不是测试失败
- OPA：`tools/opa/opa.exe` 若存在则 Gate3 OPA 测试不 skip（视本机是否已下载）
- 覆盖率：`PYTHONPATH=src python -m pytest --cov=xa_guard --cov=bench --cov-report=term -q` → **TOTAL 82%**

---

## 策略与关卡（摘要）

- **双层策略**：`policies/baseline/` + `overlay/`；`LayeredPolicySource` 合并；risk_level 唯一源 `gate4_capabilities.yaml`；merged-view Rego engine/export 已有原型
- **Gate1**：规则 + 可选模型；Spotlighting metadata 可审计；Gate1-only evaluator 拆分 rule/model/fusion/spotlighting；**Recall@1%FPR: 100%（60/60 Gate1-scope，FPR 0%）**，超标 PRD 保底 85%（2026-06-18 新增 8 条中文 PII + 2 个新 deny category）
- **Gate2–5**：风险分级 / 31 条 Gate3 / 污点 / 沙箱路由（Docker 命令构造已实现）
- **Gate6**：OTel JSONL + 哈希链；`audit_completeness` 按 CORE 字段完整率计算；国密三件套已闭合——`hash_algo=sm3` 产出真实 GB/T 32905-2016 SM3（纯 Python，无依赖，不再降级 SHA-256），`sm2_sign(prefer_gm=True)` 产出真实 GB/T 32918 SM2-with-SM3 签名（128 hex r||s），TSA 时间戳 token 可锚定 audit anchor_hash→签名 UTC 时间；本地文件 TSA anchor/index 可锚定 audit 文件字节与链摘要
- **L3 部署/接入**：Streamable HTTP 上游最小实现；Docker Compose 原型配置已补 sandbox 镜像默认构建、容器内 Docker CLI、静态工具 discovery；部署 verifier 已能区分静态配置通过、产品失败和 Docker daemon 外部不可用；无 elicitation 客户端的 pending approval fallback 已有协议内控制工具、本地 JSONL pending ledger、拒绝审计和 token one-shot；AIBOM gateway 已进入 supply_chain bench 与真实 MCP `install_plugin` 离线 preflight，并完成 OpenCode 真实 LLM 客户端调用/拦截/验链（`opencode run` 可复现，证据 `docs/evidence/opencode-smoke-audit-2026-06-18.jsonl`）；SDK `@protect` 和 LangChain `protect_tool()` 具备最小非透传 preflight
- **外部 benchmark**：AgentDojo/InjecAgent 当前有 adapter + evidence archive + 本地 XA-Guard projection 原型，能规范化用户导出、校验、生成 hash manifest，并可选写隔离 projection audit；不能作为官方 benchmark 分数

---

## 距 PRD 目标

| 级别 | 状态 |
|---|---|
| **L1 基础** | ✅ 满足 |
| **L2 工程** | ✅ **Hard 项满足**；Competition-trusted 证据闭合 |
| **L3 政企** | 🟡 原型推进中——PRD L3 三要件：①Docker 一键部署 ✅ runtime 已验收（compose build/up 实跑、容器 healthy、healthz 200、部署 verifier 6/6 pass）②国密支持 ✅ 三件套闭合（SM3 GB/T 32905 哈希链 + SM2 GB/T 32918 真实签名 + TSA 时间戳 token，证据 `docs/evidence/l3-sm2-tsa-evidence-2026-06-18.json`）③性能基准 ✅ 中等档已达（P50 20.3ms/P95 168ms/53.5 QPS/63MB）；供应链与 MCP 离线安装准入、opencode 真实链路证据已补；真实 Trae HITL、官方外部 benchmark、gVisor Linux 仍缺 |
| **L4 工业** | ❌ 未开始 |

---

## L3 差距（与 L2 清单明确分离）

1. ~~生产级国密 SM2 签名 + 外部 TSA~~ **已闭合**：SM3 哈希链（GB/T 32905-2016，纯 Python 无依赖）+ SM2 真实签名（GB/T 32918，gmssl `sign_with_sm3`/`verify_with_sm3`，128 hex r||s）+ TSA 时间戳 token（SM2 签名 anchor_hash→UTC 时间，可嵌入公钥自验，可选外部 RFC 3161 查询）；证据 `docs/evidence/l3-sm2-tsa-evidence-2026-06-18.json`；详见 `tests/unit/test_sm2_sign.py`、`test_tsa_client.py`、`test_sm3_pure.py`；本地 SM2 TSA 非第三方可信 TSA，但满足 PRD「SM2+TSA」证据形态且可离线复验；Docker Compose 一键部署 runtime 已验收，未做长期运行/soak 验收
2. **Trae / 国产 IDE 真实 HITL 弹窗**实测与截图；当前已有 MCP elicitation、pending approval fallback 和本地 pending ledger 的进程内/E2E 证据，但不等同真实客户端 UI；pending 参数脱敏支持 schema 标注优先 + 字段名回退的 L3 原型，不覆盖自由文本 DLP、完整 JSON Schema 组合关键字、KMS/DPAPI/国密加密恢复或生产 RBAC
3. **AgentDojo / InjecAgent** 官方环境复现与指标对照；当前只有离线 adapter + evidence archive + 本地 projection 原型，不能声称官方 ASR
4. **OPA/Rego 生产化**：merged-view Rego engine/export 原型已补；仍需真实 OPA CLI/服务化部署、性能评估和三层 Rego 包硬化；gVisor Linux 实测仍缺
5. **真实 marketplace/IDE 安装器集成**；当前已接真实 MCP `install_plugin` 离线 preflight，但不下载、不执行 marketplace 安装，也未拦截客户端插件商店
6. **500+ 国标完整题库**；30 页 PDF / 10 分钟视频 / 报名表
7. **完整 LangChain Callback/Tool wrapper**；Streamable HTTP 下游/多 session 压测；CoT faithfulness 实算法
8. **Faithfulness 口径仍待修复**：Gate6 当前固定写 `1.0`，只能视为占位，不能宣称已计算决策忠实度；需要调整既有测试契约后实现可重放 gate evidence

---

## 赛题四方向贴合（简表）

| 方向 | L2 现状 | L3 主要空位 |
|---|---|---|
| 1 输入攻击 | 规则 + Gate1 evaluator + Qwen 代码路径 | 模型主检测能力、自适应攻击集 |
| 2 工具安全 | Gate2–5 + layered + merged-view Rego 原型 + MCP E2E 测试 + pending approval fallback + Streamable HTTP 上游原型 + SDK/LangChain Tool preflight | 真实客户端 UI、OPA 生产部署、gVisor Linux、完整 LangChain/Agent 集成 |
| 3 供应链 | AIBOM 5 项生产化 + CLI + bench gateway + 真实 MCP `install_plugin` 离线 preflight | marketplace/IDE 安装器、实时 feed、生产签名信任根 |
| 4 评测审计 | 290 bench + 实测 audit + 前端 + 本地文件 anchor + 外部 adapter/archive 原型 | 官方外部 benchmark、正式国密链 / 外部 TSA |

---

## 下一步（L3 导向）

1. ~~Gate1：Recall@1%FPR~~ **已达标**：100% @ 0% FPR（PRD 保底 85% 超标）
2. 真实 Trae HITL 弹窗截图（opencode HITL 闭环已完成，缺 Trae GUI 截图）
3. 启动 Docker daemon 后做 Docker Compose 完整 build/up 验收与 Linux/gVisor 实测（**Docker runtime 已验收**，缺 gVisor Linux）
4. 完整 LangChain SDK 全链路集成
5. AgentDojo / InjecAgent 官方复现
6. 扩充 bench 从 290 → 500+ 用例
7. 交付物：PDF / 视频 / 报名
8. faithfulness 算法（仍固定 1.0，涉及既有测试契约需用户审核）
