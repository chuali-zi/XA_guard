# 仓库状态 · XA-Guard / XA-202620

> 本文件描述**当前仓库状态**（差什么、需要改什么、距 PRD 还有多远），不是工作日志。
> 工作流水记 `log.md`；L2 冻结清单见 `docs/L2-acceptance-checklist.md`；验证命令见 `docs/L2-verification-commands.md`。
> 快照时间：2026-06-19 +08:00

---

## 一句话定位

**L2 工程完成（Hard + Competition-trusted 口径）**：6 关卡 pipeline 可跑、**覆盖率 82%**（≥50% L2 Hard）、290 条 XA-Bench、Gate1-only evaluator、覆盖矩阵、Gate3 fixtures、Gate5 Docker sandbox、审计验链。L3 政企原型已具备 Docker Compose、**stateful Streamable HTTP 真多会话**、HITL pending approval、AIBOM gateway、严格 SM2/真实 SM3/TSA、OPA/SDK/外部 benchmark adapter 原型。OS 审计锁硬化后 10 会话/500 请求真实 HTTP MCP 基准：P95 153.117ms、92.981 QPS、103.836MB，500/500 无错误无串话、审计 marker 全匹配且验链通过；OpenCode/GLM-5.2 已真实通过 HTTP MCP 调用 `get_cpu`（trace `cf2f194f`）。PRD L3 三要件（Docker 一键部署 / 国密支持 / 性能基准）**均已闭合**；但 **PRD L3 仍未整体达成**（AgentDojo/InjecAgent 官方复现、gVisor Linux、500+ 题库、完整 LangChain wrapper、真实客户端 UI、faithfulness 算法仍缺）。

---

## L2 工程完成（客观陈述）

| 维度 | 状态 | 证据 |
|---|---|---|
| **Hard L2（PRD §4.2）** | ✅ | LOC ≈ 7900+（src+bench）；README 已对齐当前策略目录与命令；`pytest --cov` **82%**；6 关单元测试齐全 |
| **全量 pytest** | ✅ 当前工作树零失败 | 2026-06-19 全仓回归 100% 完成且 0 failed；2 个环境 skip：未安装 `langchain_core`，当前测试上下文不可见 `xa-guard/sandbox:latest`。Docker build/up/health 6/6 与真实 sandbox 属于此前同工作树的独立实测证据；AgentDojo/OpenCode bridge/normalizer 聚焦 12 passed |
| **XA-Bench 290** | ✅ | `python -m bench.cli run …` → pass_rate 100%，`audit_completeness=1.0`（265 条走 pipeline 写审计） |
| **Gate1-only evaluator** | ✅ 赛题点值达标；独立统计验收待补 | `python scripts/evaluate_gate1.py --detectors rule`；Gate1-scope 60 attack：检测召回与阻断召回均 **100%**；76 个 benign controls 中仅 58 个 oracle=allow 进入 FPR 分母，观测 FPR **0%**，18 个非 allow control 明确排除；全治理域对照单列为 35.75%，不再污染 Gate1 分母；legacy 精确规范化 payload 诊断切分 29/33 校准、31/25 留出，跨 split exact-payload 重叠 0，双方均为 100%/0%。但该 seed 已参与开发，且 0/58 的 FPR 95% Wilson 上界为 6.21%，仍需每 split 至少 381 个未见 allow-negatives 才能做 formal 1% FPR 强统计验收。证据：`docs/evidence/gate1-l3-evaluation-2026-06-18.json` |
| **Gate1 外部 holdout 协议** | ✅ 协议与 smoke 闭环；正式数据待独立评测方 | `bench/gate1_holdout.py` + `scripts/gate1_holdout.py` 已实现 system lock、manifest/oracle/payload/semantic-group commitment、calibration threshold lock、holdout 固定阈值复算、JSON Schema 与非零失败。默认 formal 强制 clean Git、独立 attestation、人工 semantic group、每 split 六类 attacks 各≥20 + 381 allow-negatives，以及 FPR 点估计/95% Wilson 上界均 ≤1%；当前仓库只提交 1+1/1+1 的 `smoke` 证据，明确 `independent_holdout=false`，不能充当正式成绩。协议：`docs/gate1-holdout-protocol.md` |
| **覆盖矩阵** | ✅ | `--strict`：tools=48 / gate2=48 / gate4=48 / bench_only=0 |
| **Gate3 fixtures** | ✅ | 31 规则 × 正/反例，`validate_gate3_rule_fixtures.py --strict` errors=0 |
| **审计完整率** | ✅ 已实测 | `bench/metrics.py` 聚合 Gate6 `audit_completeness`；非固定占位 |
| **Bench 证据可信度** | ✅ 全样本闭环 | 缺审计按 0 进入总分母；infra error 单列且不进入 ASR/FPR/CuP；CLI 对 infra/缺审计/不完整审计非 0；`last_results.json` 保留 trace、record hash、审计与错误字段，可离线复算同一报告 |
| **Gate5 沙箱镜像** | 🟡 代码与历史证据可用，当前环境待恢复 | 历史已在本机构建 `xa-guard/sandbox:latest` 并通过真实沙箱测试；本轮 Docker Desktop daemon 未启动，本地镜像不可用导致集成测试 skip |
| **L3 部署入口** | ✅ 当前 runtime + 多会话协议验收 | `docker-compose.yml` + Dockerfiles + `configs/xa-guard.docker.yaml`；`StreamableHTTPSessionManager(stateless=False)` 为每个客户端签发独立 session ID，支持 DELETE 回收和 idle timeout；`/healthz` 暴露 stateful/active_sessions/timeout。当前工作树已重建 `xa-guard:latest` 与 sandbox 镜像，Compose build/up/health 6/6 pass，health body 为 stateful/active_sessions=0/timeout=300；真实 sandbox 禁网与只读 rootfs 测试通过。证据 `docs/evidence/l3-deployment-verification.json` |
| **L3 性能基准** | ✅ in-process + HTTP MCP 中档证据 | 进程内 500/并发10：P50 20.305ms、P95 168.273ms、53.486 QPS、62.996MB。OS 审计锁硬化后真实 uvicorn/stateful MCP/stdio 下游 500/10 session：P50 98.030ms、P95 153.117ms、92.981 QPS、103.836MB，500/500 无错误/串话，500 条审计 marker 一一对应且验链；20 session 历史饱和压力 P95 417.849ms 未达门槛。证据 `docs/evidence/l3-streamable-http-benchmark-2026-06-18.json` |
| **L3 供应链准入** | 🟡 原型 | bench supply_chain 与真实 MCP `tools/call install_plugin` 均走 AIBOM gateway；本地目录/归档和 hash 可扫描，服务端离线缓存命中的远程引用可扫描，未镜像远程引用 fail-closed；仍非真实 marketplace/IDE 安装器 |
| **L3 SDK 非透传** | 🟡 原型 | `xa_guard.protect` / `xa_guard.sdk.protect` 已在调用原函数前跑 pipeline preflight；`xa_guard.integrations.langchain.protect_tool()` 支持单个 BaseTool 强阻断 wrapper；当前环境未安装 langchain-core，集成测试 skip |
| **L3 审计锚定** | 🟡 原型 | `scripts/anchor_audit.py` 生成本地文件 TSA anchor；manifest 覆盖 audit 文件 SHA-256、字节数、记录数、首尾 record_hash，并写 `anchors/index.jsonl` 串联；这不是外部可信 TSA |
| **L3 外部 benchmark** | 🟡 AgentDojo + InjecAgent 官方代码单例 protocol/defended smoke + 离线 adapter | AgentDojo 固定 0.1.35 / commit 089ed468 / MIT；现有首对 standalone injection utility=false 且旧 prompt 有防御污染，不能计正式 ASR。InjecAgent 固定 commit f19c9f2 / MIT，官方数据 510 DH + 544 DS；原版 prompt/parser/scorer 已跑通 DH case 0 的 base、enhanced baseline、enhanced XA-Guard defended，以及 DS case 0 base S1，4 次均 valid/attack_success=false。defended 记录 Gate1 deny 和完整 enhanced 指令清洗；DS 因 S1 未成功而 eval_step_2=null。全部 evidence official_claim=false；单例不能代表总体 ASR，S2 实链与 1054 例批量矩阵仍未完成 |
| **L3 OPA/Rego** | 🟡 原型 | `Gate3 backend=rego + prefer_layered` 可使用 LayeredPolicySource merged rules；`scripts/export_opa_policy.py` 可导出 OPA `data.json` + `gate3.rego` + manifest；真实 OPA CLI 运行视本机 binary |
| **L3 HITL fallback** | 🟡 原型 → ✅ `opencode run` 实测闭环 | 上游 MCP 内置 `xa_guard_list_pending_approvals` / `xa_guard_approve_pending`；无 elicitation 客户端会暂存红色工具调用；`pending_approvals_path` / `XA_GUARD_PENDING_APPROVAL_STORE` 可启用本地 JSONL pending ledger，支持单机重启恢复未过期非敏感 pending 项；ledger/list 优先按工具 `inputSchema` 的敏感标注脱敏并字段名回退；**真实 `opencode run` 端到端闭环已验证**：glm-5.2 调用 `pending_approval_op` → Gate2 REQUIRE_APPROVAL → pending staging → `xa_guard_approve_pending(approve=true, approver=ops-lead)` → 下游执行 → 审计链 `require_approval → allow`（2 records, 0 errors, trace `2eed0319`），证据 `docs/evidence/l3-hitl-pending-approval-2026-06-18.md`；真实国产 IDE Trae 弹窗截图仍待补 |

**Competition-trusted L2 当前已闭合**：真实 Qwen GPU 复跑 Gate1、真实 IDE HITL 截图归入 L3/冲刺证据——见 L3 段。

---

## 测试状态
- 2026-06-19 InjecAgent official-code smoke: pinned f19c9f2, upstream 510 DH + 544 DS. Direct-harm case 0 base, enhanced baseline, and enhanced XA-Guard defended all scored valid/attack_success=false with the unmodified upstream parser/get_score; defended Gate1 denied and removed the full enhanced instruction. All 13 referenced artifact hashes across four summaries match; these remain single-case protocol evidence, not aggregate ASR.
- 2026-06-19 Windows audit-lock regression: full pytest once exposed two concurrent genesis records at line 2. Production locking now uses a path-derived Windows kernel named mutex (POSIX remains flock); Merkle suite 11 passed, 20 repeated spawn/crash-recovery rounds passed, Ruff/compileall passed.
- 2026-06-19 post-fix full repository pytest: 100% complete, zero failures, two environment skips (langchain_core absent; local sandbox image unavailable to the test context).
- 2026-06-19 AgentDojo evidence integrity: all 6 referenced artifact SHA-256 values across the three retained summaries match. Failed neutral/early-defense run directories and temporary patch files were removed; retained results remain limited smoke evidence, not efficacy or leaderboard claims.
- 2026-06-19 external bridge regression: `tests/unit/test_opencode_bridge.py + test_external_benchmarks.py` 12 passed; Ruff and compileall passed. Official AgentDojo single-pair trace hashes and 9 invocation records were independently recomputed.
- 2026-06-19 full repository pytest reached 100% with zero failures and two environment skips: missing `langchain_core` and sandbox image unavailable in the current test context.

- 本轮严格 SM2/审计锁硬化后最终全量：`python -m pytest -q --basetemp pytest_tmp_l3_sm2_full -p no:cacheprovider -x --tb=short`：100% 通过，仅 1 skip（未安装 `langchain_core`）；真实 Docker sandbox 已执行而非跳过；本轮变更文件 Ruff、`compileall`、`git diff --check` 通过，benchmark 脚本/config/raw/audit hash 与 targets 自校验全 true
- 本轮当前 Docker runtime：部署 verifier 初次因默认宿主端口错误（3000 而非 Compose 13000）、第二次因 urllib 继承系统代理而假阴性；修正默认 URL 和 loopback no-proxy 后 `--run-build --run-up` 6/6 pass，health 200 且返回 stateful/active_sessions=0/timeout=300。隔离 `DOCKER_CONFIG` 后真实 sandbox + Compose 测试 2 passed
- Docker 当前状态：已用包含严格 SM2 与 OS 审计锁代码的当前工作树重建；`verify_l3_deployment.py --run-build --run-up` 6/6 pass，health 为 stateful/active_sessions=0/timeout=300；真实 sandbox 禁网与只读 rootfs 测试通过，`docker compose down` 已成功清理容器与网络
- 历史 L2 闭合：`PYTHONPATH=src python -m pytest -q --basetemp pytest_tmp_full_after_sandbox -p no:cacheprovider -x --tb=short`：**394 passed / 0 skipped / 0 failed**
- `python -m pytest -q --basetemp pytest_tmp_l3_full -p no:cacheprovider -x --tb=short`：全量通过（进度 100%，无失败）
- `python -m bench.cli run --suite bench/cases/csab-gov-mini-seed.yaml --config configs/xa-guard.yaml`：290 条 pass_rate **1.0**，`audit_completeness=1.0`，P50 **75.14 ms**，P95 **558.4 ms**（P95 尚未达 PRD 中等档 300 ms）
- Gate5 sandbox：当前 `xa-guard/sandbox:latest` 已由工作树重建并真实执行通过，验证禁网 + 只读 rootfs；对应 Docker 部署证据 6/6 pass
- Streamable HTTP：真实 ASGI/MCP E2E 以 4 个并发 `ClientSession` 验证 4 个唯一 session ID、marker 零串话、伪造 session 404、4 条唯一 trace 审计、DELETE 后 active_sessions=0；配置/协议定向测试 6 passed
- Streamable HTTP 性能：`python scripts/benchmark_streamable_http.py --sessions 10 --requests 500 --warmup 20 ... --require-targets` 全 targets 通过；P50 98.030ms、P95 153.117ms、92.981 QPS、103.836MB，500 个 request marker 与 500 条完整审计精确匹配，链通过
- OpenCode HTTP：隔离目录 + `NO_PROXY` 下，`opencode.cmd mcp list` 显示唯一 `xa_guard_l3_http connected`；GLM-5.2 产生 `xa_guard_l3_http_get_cpu(host=web03)` 调用并返回 85%，trace `cf2f194f-087a-4ad7-884c-dac817c3b763`，审计 1 record / 0 errors；首次受系统代理影响而回退 stdio 的尝试明确判为无效证据
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
- Gate1 指标口径/fusion 修复后全量 pytest 100% 通过，2 skip 原因不变；首次回归暴露的 `api_key` 字段名误杀已在实现层收窄并由 pending-ledger 集成测试验证
- Gate1 外部 holdout 协议新增 13 项定向测试并完成全量 pytest 回归；全量 100% 通过，仍只有上述 2 个环境性 skip
- OPA：`tools/opa/opa.exe` 若存在则 Gate3 OPA 测试不 skip（视本机是否已下载）
- 覆盖率：`PYTHONPATH=src python -m pytest --cov=xa_guard --cov=bench --cov-report=term -q` → **TOTAL 82%**

---

## 策略与关卡（摘要）

- **双层策略**：`policies/baseline/` + `overlay/`；`LayeredPolicySource` 合并；risk_level 唯一源 `gate4_capabilities.yaml`；merged-view Rego engine/export 已有原型
- **Gate1**：规则 + 可选模型；Spotlighting metadata 可审计；Gate1-only evaluator 拆分 rule/model/fusion/spotlighting；`secret_exfil` / `forbidden_generation` 已纳入 fusion 默认 deny 类目；**名义 Recall@1%FPR: 100%（60/60 Gate1-scope，阻断召回同为 100%，58 个 allow negative controls 观测 FPR 0%）**，超过 PRD 保底 85%。评估器已将 Gate1 六类输入攻击与其他治理域分开，并增加剔除 `variant_index` 的语义 payload 固定诊断切分；当前规则 score 仍只有 0/1，且未见外部冻结集尚缺。
- **Gate2–5**：风险分级 / 31 条 Gate3 / 污点 / 沙箱路由（Docker 命令构造已实现）
- **Gate6**：OTel JSONL + 前向哈希链；`audit_completeness` 按 CORE 字段完整率计算；`hash_algo=sm3` 产真实 GB/T 32905-2016 SM3；`signature_mode=sm2` 为严格 SM2-with-SM3，缺库/私钥 fail-closed，算法与 key ID 纳入记录哈希，正式 verifier 可逐条强制验签；HMAC 仅显式 `hmac-demo`。hash→签名→单次 append 位于共享 OS 文件锁内，40 线程、4 进程/80 条、持锁进程崩溃恢复均有测试；TSA token/anchor 仍为本地可验证原型，非第三方可信 TSA
- **L3 部署/接入**：Streamable HTTP 已升级为 stateful 真多会话，独立 session ID/生命周期/健康指标/并发隔离均有协议测试和 500 请求证据；Docker Compose 具备 sandbox 镜像、容器内 Docker CLI、静态工具 discovery；无 elicitation 客户端 pending approval 已有控制工具、本地 ledger、拒绝审计和 token one-shot；AIBOM gateway 已进入真实 MCP `install_plugin` preflight；OpenCode 已分别完成 stdio HITL/AIBOM 和 HTTP allow 调用实测；SDK `@protect` 和 LangChain `protect_tool()` 具备最小非透传 preflight
- **外部 benchmark**：AgentDojo 官方 protocol/defended 单对 OpenCode smoke 已落 trace；Gate1 对真实注入工具输出 deny 并保留业务数据。旧 prompt 自带防御提示且首对不具备 ASR 资格，只证明链路和防御钩子执行，不证明增量效果；中性矩阵及 InjecAgent 官方环境仍缺

---

## 距 PRD 目标

| 级别 | 状态 |
|---|---|
| **L1 基础** | ✅ 满足 |
| **L2 工程** | ✅ **Hard 项满足**；Competition-trusted 证据闭合 |
| **L3 政企** | 🟡 原型推进中——PRD L3 三要件：①Docker 一键部署 ✅ 当前多会话镜像 build/up/health 6/6，真实 sandbox 测试通过 ②国密支持 ✅ SM3/SM2/TSA 三件套闭合 ③性能基准 ✅ 进程内与真实 HTTP MCP 均达中档；供应链准入、OpenCode stdio/HTTP 真实链路已补；真实 Trae HITL、官方外部 benchmark、gVisor Linux、500+ 题库、完整 LangChain 与 faithfulness 仍缺 |
| **L4 工业** | ❌ 未开始 |

---

## L3 差距（与 L2 清单明确分离）

1. **严格 SM2 审计签名已闭合；外部可信 TSA/HSM 未闭合**：SM3 哈希链（GB/T 32905-2016，纯 Python 无依赖）+ strict SM2-with-SM3 原子逐记录签名（GB/T 32918，缺 key/gmssl fail-closed，算法与 key ID 入链，CLI 可逐条强制验签）+ 本地 TSA token；证据 `docs/evidence/l3-sm2-tsa-evidence-2026-06-18.json`，详见 `tests/unit/test_sm2_sign.py`、`test_tsa_client.py`、`test_sm3_pure.py`、`test_gate6_audit.py`。本地 TSA 不是第三方可信 TSA，生产密钥仍需 HSM/KMS、轮换与外部时间锚；Docker Compose 当前 runtime 6/6 已验收，未做长期 soak
2. **Trae / 国产 IDE 真实 HITL 弹窗**实测与截图；当前已有 MCP elicitation、pending approval fallback 和本地 pending ledger 的进程内/E2E 证据，但不等同真实客户端 UI；pending 参数脱敏支持 schema 标注优先 + 字段名回退的 L3 原型，不覆盖自由文本 DLP、完整 JSON Schema 组合关键字、KMS/DPAPI/国密加密恢复或生产 RBAC
3. **AgentDojo / InjecAgent**：AgentDojo 官方代码/scorer protocol smoke 与 XA-Guard defense hook 已完成；中性 adapter 已去掉额外防御提示，但真实中性 baseline/defended 完整重跑仍受外部模型超时阻断。仍需完成合格批量矩阵、正式 ASR/Utility、论文模型对照及 InjecAgent
4. **OPA/Rego 生产化**：merged-view Rego engine/export 原型已补；仍需真实 OPA CLI/服务化部署、性能评估和三层 Rego 包硬化；gVisor Linux 实测仍缺
5. **真实 marketplace/IDE 安装器集成**；当前已接真实 MCP `install_plugin` 离线 preflight，但不下载、不执行 marketplace 安装，也未拦截客户端插件商店
6. **500+ 国标完整题库**：现有 290 个物理回归行最多对应 239 个语义 case、218 个规范化唯一 payload，L3 规模未达；另需 30 页 PDF / 10 分钟视频 / 报名表
7. **完整 LangChain Callback/Tool wrapper**；Streamable HTTP 下游 transport（上游多 session 已完成）；CoT faithfulness 实算法
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

1. Gate1：当前 seed 的赛题点值与外部验收协议均已闭环；仍需独立评测方在策略冻结后提供/保管正式数据（每 split 六类 attacks 各≥20 + ≥381 allow-negatives）、attestation 和预先公开/可信时间戳摘要，再运行 formal profile。现有 legacy diagnostic 与 smoke 证据均不冒充独立 holdout
2. 真实 Trae HITL 弹窗截图（opencode HITL 闭环已完成，缺 Trae GUI 截图）
3. 启动 Docker daemon 后做 Docker Compose 完整 build/up 验收与 Linux/gVisor 实测（**Docker runtime 已验收**，缺 gVisor Linux）
4. 完整 LangChain SDK 全链路集成
5. AgentDojo / InjecAgent 官方复现
6. 扩充 bench 从 290 → 500+ 用例
7. 交付物：PDF / 视频 / 报名
8. faithfulness 算法（仍固定 1.0，涉及既有测试契约需用户审核）
