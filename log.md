# 工作日志

## 2026-06-18 ZCode 主 agent - L3 多 git 回滚基线 + opencode 实测链路 + 真实 SM3 国密哈希链

本次具体做了什么：
- 按用户三点注意事项执行：①「多 git 方便回滚」②遵守 AGENTS.md（log 顶层加、status 描述当前状态不顶层堆日志、不靠改测试通过测试）③实际测试用 `opencode run "message"`。
- 先核对 `status.md`/`log.md`/`docs/PRD.md`：当前未提交的 L3 原型工作横跨 50 文件 +6227/-1118 行，但全部停留在工作区。`compileall src/bench/scripts/tests` 通过；L3 定向回归 117 passed（pipeline/mcp-e2e/aibom/pending/upstream/config/gate5/gate3/tsa/external/opa/sdk）。
- 建立 git 回滚基线：commit `d741209` 把全部已验证通过的 L3 原型栈一次性 checkpoint（Docker/Streamable HTTP/HITL pending+ledger+schema 脱敏+AIBOM 真实 MCP install_plugin 准入/SDK+LangChain preflight/本地 TSA anchor/可复现性能基准/外部 benchmark adapter+projection/OPA merged-view 导出/bench 全样本审计可信口径/L3 部署 verifier），便于后续每步可回滚。
- 修复一个工具垃圾文件：之前 `2>nul` 在 git-bash 下被当成真实文件 `nul`，用 `rm` 清理。
- 接通 `opencode run` 实测链路：发现仓库根缺 `opencode.json`（opencode 从 CWD 读 MCP 配置），`opencode mcp list` 报 No MCP servers。新建根 `opencode.json`（本地运行配置，加入 `.gitignore`，规范 smoke 配置仍保留在已跟踪的 `configs/opencode.l3-smoke.json`），选用 `opencode-go/glm-5.2` 模型。`opencode mcp list` → `xa_guard_l3_smoke connected`。
- 真实 LLM 端到端实测：`opencode run "…"` 让 glm-5.2 真实调用 `xa_guard_l3_smoke_install_plugin`，传入恶意 `code_snippet`（`subprocess.Popen` + `urllib.request.urlopen('http://evil.example.com/...')`）。AIBOM 网关判 grade F（process_exec + network + 可疑外部端点），在 HITL 前直接 deny，下游安装 0 次执行（result.hash=空 SHA-256）。
- 验链：`scripts/verify_audit.py --path logs/opencode-smoke/audit.jsonl` → 1 record，trace `8301978d-b4bc-482d-a6b1-ff3b5270e62b`，rule hit `AIBOM-GATEWAY`，decision=deny，0 chain/hash errors，0 missing-field records。把该 audit 作为证据 `docs/evidence/opencode-smoke-audit-2026-06-18.jsonl`（`.gitignore` 加 `!docs/evidence/**` 让证据可提交），commit `3893813`。
- 推进 L3 国密 SM3 哈希链（PRD 国密合规 4 分 + 审计法律效力）：发现 `src/xa_guard/audit/sm_crypto.py` 在 gmssl 不可用时 `sm3_hash(prefer_gm=True)` 会**静默降级 SHA-256**，导致标 `hash_algo=sm3` 的审计记录实际是 SHA-256，是伪加密隐患。
- 新增 `_sm3_pure()`：纯标准库 SM3（GB/T 32905-2016），改 `sm3_hash(prefer_gm=True)` 为「gmssl 优先 → 否则纯 Python SM3 → 永不降级 SHA-256」。调试中修正三处真实 bug：`P1` 用 23 不是 17、W 扩展 `rotl(w[j-13],7)` 不是 17、压缩轮 `E=P0(tt2)` 不是 `rotl(tt2,7)`，并修正常量 `T_j` 应为 `0x79CC4519`（之前误写 `0x79345900`）。
- 用 gmssl 作为交叉验证 oracle（仅测试用，非运行时依赖）：`_sm3_pure` 对 empty/abc/64×abcd/1000×a/range256/全零/全 ff 全部与 gmssl 一致；空串命中 GB/T 32905 标准向量 `1ab21d83…aa2b`。
- 新增 `tests/unit/test_sm3_pure.py`（5 passed）：GB/T 标准向量、gmssl 口径一致（无 gmssl 则 skip）、`prefer_gm=True` 不降级 SHA-256、确定性 + 与 SHA-256 区分、SM3 哈希链可写可验且 record_hash 是真实 SM3。
- 验证现有测试契约未被破坏：`test_gate6_sha256_fallback_on_sm3_unavailable` 仍通过（其契约只断言 hex + `hash_algo=='sm3'`，真实 SM3 同样满足；未修改任何既有测试）。SM3 相关宽回归 46 passed。端到端 SM3 链 demo：`ChainStore(algo='sm3')` 写 5 条 + verify 通过，record_hash 与 `_sm3_pure` 一致、与 SHA-256 不同。
- commit `565d82e` 为 SM3 国密哈希链 checkpoint。

验证：
- `python -m compileall -q src bench scripts tests`：通过。
- L3 定向回归：117 passed（commit 前基线）。
- `opencode mcp list`：`xa_guard_l3_smoke connected`。
- `opencode run "…install_plugin…恶意 code_snippet…"`：LLM 真实调用工具 → AIBOM grade F → deny，下游 0 次执行。
- `scripts/verify_audit.py --path logs/opencode-smoke/audit.jsonl`：1 record，0 chain/hash errors，0 missing-field。
- `tests/unit/test_sm3_pure.py`：5 passed。
- SM3 宽回归（gate6/merkle/tsa/archive/pipeline/verify_cli/bench_truth/aibom）：46 passed。
- git commits：`d741209`（L3 原型栈 checkpoint）、`3893813`（opencode smoke harness + AIBOM 证据）、`565d82e`（真实 SM3 国密哈希链）。

未完成 / 客观限制：
- **未推送远端**：三个 commit 都在本地 `main`，按用户「多 git 方便回滚」意图保留为本地回滚点；是否 push 待用户确认。
- SM2 真实签名仍是 HMAC-SHA256 fallback（需要 gmssl PEM 私钥或 cryptography SM2 插件才能产真实 SM2 签名），本轮只闭合 SM3 哈希链，未做 SM2 签名生产化。
- gmssl 仅作为本机交叉验证 oracle 安装，不是运行时依赖；纯 Python SM3 是无第三方依赖的合规实现。
- 根 `opencode.json` 是本机运行配置（已 gitignore），其他机器复现需参考 `configs/opencode.l3-smoke.json` 自行落地。
- PRD L3 仍未整体完成：Docker daemon 当前未启动，完整 Compose build/up 仍未验收；真实 Trae/国产 IDE HITL 弹窗截图、外部 TSA、AgentDojo/InjecAgent 官方复现、gVisor Linux、500+ 题库、完整 LangChain wrapper、Gate1 Recall@1%FPR、faithfulness 算法（仍固定 1.0）仍待补。
- faithfulness 固定 1.0 涉及既有测试契约，按 AGENTS.md 未单方面改测试，需用户审核后再动。

下一步：
- 启动 Docker Desktop 后做 Docker Compose 完整 build/up/healthz 验收（补 L3 一键部署 runtime 证据）。
- 真实 Trae HITL 弹窗实测与截图（PRD 硬承诺）。
- SM2 真实签名生产化（gmssl PEM 或 cryptography SM2 插件）+ 外部 TSA。
- 与用户确认是否 push 三个本地 checkpoint 到远端。

## 2026-06-18 Codex 主 agent（+5 gpt-5.5 medium 子 agent）- Bench 全样本审计与 infra error 可信口径

本次具体做了什么：
- 继续 L3 目标，派出 5 个 `gpt-5.5 medium` 子 agent：3 个只读审查 bench/runner/Gate6，2 个在互不冲突的新测试文件中补回归测试。审查确认 audit completeness 分母、异常吞掉、supply-chain 绕 Gate6、结果不可离线复算和 verifier 非法 JSON 崩溃均为真实问题。
- 修改 `Pipeline`：新增集中 `_audit()`，所有预置 deny、Gate1/Gate2-4/Gate5 短路、executor 异常、approval token 失败、审批后异常和 reject 路径都将 Gate6 结果 append 到共享上下文；新增 `finalize_preflight()` 供 AIBOM 等领域预检只写审计、不重跑通用 gate。
- 修复 executor 异常时 `PipelineResult` 为 deny 但 `ctx.final_decision` 仍为 allow 的不一致，现统一 fail-closed 为 deny。
- 修改 bench runner：supply-chain AIBOM 路径写 Gate6；任何 pipeline/AIBOM 异常都标记 `infra_error`、deny、`passed=False`，并尽力写异常审计；Gate6 本身失败时明确留作缺审计，不能伪装为正常安全决策。
- 扩展 `BenchResult` 与 CLI 结果：保存 trace_id、audit record hash、审计完整率、infra error 类型/消息和真实 result note；旧 JSON 缺字段时仍按默认值兼容。离线 report 重建后可复算完全相同 metrics。
- 修正 metrics：审计完整率按所有操作为分母；infra error 不进入 ASR/FPR/CuP 正常样本分母；新增 evaluated/infra/audit missing/incomplete 指标。CLI 发现 infra error、缺审计或不完整审计时非 0 退出。
- 修复 `scripts/verify_audit.py` 非法 JSON 导致未定义变量崩溃；verifier/archive 统一拒绝 NaN/Infinity。
- 新增 `tests/unit/test_bench_runner_evidence.py`、`test_bench_evidence_truth.py`、`test_verify_audit_cli.py`，并更新 README/status/bench/scripts worklog。

验证：
- 证据可信度定向/宽回归共 27 passed，Ruff 通过。
- `python -m bench.cli run --suite bench\cases\csab-gov-mini-seed.yaml --config configs\xa-guard.yaml`：退出 0；290 total/evaluated，0 infra error，0 audit missing/incomplete，audit completeness 1.0，pass rate 1.0。
- `bench/.log/last_results.json`：290 行、290 唯一 trace、290 audit record hash；离线重建 metrics 与 `last_report.json` 完全一致。
- `python scripts\verify_audit.py --path logs\audit\audit.jsonl`：28,095 records，0 chain/hash errors，0 JSON parse errors，0 missing-field records。
- `python -m pytest -q --basetemp pytest_tmp_l3_truth_full -p no:cacheprovider -x --tb=short`：全量 100% 通过；2 skip（未安装 `langchain_core`、本机无 Docker sandbox 镜像）。

未完成 / 客观限制：
- Gate6 的 `gen_ai.decision.faithfulness_score` 仍固定为 1.0，是未实现算法的占位，不能作为忠实度已验证证据；现有测试也固定断言 1.0，按项目规则本轮未擅自改测试契约。
- 当前 evidence 可证明每个 case 与审计记录一一关联并离线复算 metrics，但尚未保存足够的逐 gate 输入/metadata/策略快照做完整 decision replay。
- Gate1 Recall@1%FPR 仍未达 PRD 保底；Docker runtime、生产 SM2/SM3 与外部 TSA 仍未完成。

## 2026-06-18 Codex 主 agent（+4 gpt-5.5 medium 子 agent）- L3 可复现性能基准

本次具体做了什么：
- 对照 `docs/PRD.md` 的 L3 定义重新审计缺口：L3 核心为 Docker 一键部署、国密支持、性能基准。派出 4 个 `gpt-5.5 medium` 子 agent 分别审查 PRD、LangChain、审计可信度和性能测试；3 个只读审查，1 个仅新增性能测试文件。
- 新增 `scripts/benchmark_l3_performance.py`：运行真实六关卡 pipeline 与 Gate6 JSONL 落盘，混合 allow/deny/approval 三类 workload；输出 `xa-l3-performance-benchmark/v0.1` JSON，包含脚本/config SHA-256、环境、P50/P95/P99/QPS、Windows Working Set/Peak RSS、决策分布、审计记录数和哈希链校验。
- benchmark 每次创建独立 audit run 目录，不覆盖历史证据；支持 `--require-targets`，未达到 PRD 中等档时非 0 退出。
- 子 agent 新增 `tests/unit/test_l3_performance_benchmark.py`，覆盖报告 schema、延迟/吞吐/内存字段、decision counts、CLI JSON 输出和非法参数。
- 生成可版本化证据 `docs/evidence/l3-performance-benchmark-2026-06-18.json`，并更新 README、status 与 scripts worklog。

验证：
- `python scripts\benchmark_l3_performance.py --config configs\xa-guard.opencode-smoke.yaml --requests 500 --warmup 30 --concurrency 10 --audit-dir logs\performance --output docs\evidence\l3-performance-benchmark-2026-06-18.json --require-targets`：P50 20.305ms、P95 168.273ms、QPS 53.486、峰值 RSS 62.996MB；四项 PRD 中等档 target 全部通过；530 条含 warmup 的 Gate6 审计记录验链通过。
- `python -m pytest -q --basetemp pytest_tmp_l3_perf_tests -p no:cacheprovider tests\unit\test_l3_performance_benchmark.py -x --tb=short`：7 passed。
- `python -m pytest -q --basetemp pytest_tmp_l3_perf_broad -p no:cacheprovider tests\unit\test_l3_performance_benchmark.py tests\test_pipeline_smoke.py tests\unit\test_gate6_audit.py tests\unit\test_config.py tests\integration\test_mcp_e2e.py tests\unit\test_aibom_gateway.py -x --tb=short`：37 passed；`compileall`、Ruff、evidence 脚本 hash/targets 校验和 `git diff --check` 通过。

未完成 / 客观限制：
- 该性能证据是 Windows 本机、单进程、规则模式、in-process pipeline + Gate6 落盘；不包含 MCP stdio/HTTP、真实模型推理、真实工具耗时、Docker 网络或多机 soak，不能外推为生产部署性能。
- PRD L3 仍未整体完成：Docker daemon 当前不可用，完整 Compose build/up/healthz 尚未验收；国密实现仍有 fallback/演示密钥，未形成生产 SM2/SM3 + 外部 TSA 可信链。
- 子 agent 另发现 Gate1 Recall@1%FPR、bench 审计分母/faithfulness 口径和 LangChain 真实执行纳管仍有实质缺口，后续应继续修复，不能因本轮性能达标而忽略。

## 2026-06-18 Codex 主 agent（+3 gpt-5.5 medium 子 agent）- L3 AIBOM 真实 MCP 安装前准入

本次具体做了什么：
- 继续 L3 目标，派出/复用 3 个 `gpt-5.5 medium` 子 agent 做只读审查；结论一致建议把 AIBOM 从 bench 旁路前移到真实 MCP `tools/call install_plugin`，子 agent 未修改文件。
- 修改 `src/xa_guard/aibom/gateway.py`：`admit_install_request()` 支持 `artifact_path/plugin_path/archive_path/path/file` 本地目录或归档和 `expected_sha256`，通过 `scan_artifact()` 做真实解包、AST/依赖扫描与摘要校验；远程 URL 只有传入服务端离线缓存时才解析缓存字节。
- 修改 `src/xa_guard/proxy/upstream.py`：真实 `install_plugin` 调用在 6 关卡前执行 AIBOM preflight，并注入 `aibom_gateway` GateResult；D/F 或远程未镜像引用直接 deny，不触达下游；A/B/C 继续服从既有 Gate2/Gate3/HITL。支持服务端环境变量 `XA_GUARD_AIBOM_OFFLINE_CACHE` 指向预置 `OfflinePackageStore`。
- 扩展 AIBOM gateway 单元测试、upstream 单元测试和 MCP E2E fixture：覆盖本地 zip/hash、hash mismatch、离线镜像命中、远程未镜像 fail-closed、恶意插件下游 0 次、干净本地插件 HITL approve 后下游 1 次，以及 Gate6 `AIBOM-GATEWAY` 审计命中。
- 更新 `README.md`、`status.md` 和 AIBOM 模块 worklog，客观标注这是 MCP 参数面离线安装前准入，不是 marketplace/IDE 插件商店集成。

验证：
- `python -m pytest -q --basetemp pytest_tmp_l3_aibom_mcp2 -p no:cacheprovider tests\unit\test_aibom_gateway.py tests\unit\test_upstream_elicitation.py tests\integration\test_mcp_e2e.py tests\test_aibom_bench_supply_chain.py -x --tb=short`：31 passed。
- 根据用户补充的实际链路，新增 `configs/xa-guard.opencode-smoke.yaml` 与 `configs/opencode.l3-smoke.json`，并给 demo 下游增加不执行真实安装的模拟 `install_plugin`。`opencode.cmd mcp list` 显示 `xa_guard_l3_smoke connected`。
- 两次 `opencode.cmd run` 均由真实 LLM 调用 `xa_guard_l3_smoke_install_plugin`；第二次在首因短路修复后返回 `aibom_gateway: AIBOM grade F`，命中 `AIBOM-GATEWAY`，trace `e4abab76-9b3d-4556-8d08-06be6bcc77ce`，未执行下游安装。
- 修改 `pipeline.run()`：若协议适配器已注入 DENY preflight，则立即走 Gate6 审计并返回，避免后续通用 gate 覆盖供应链首个拒绝原因。
- `python -m pytest -q --basetemp pytest_tmp_l3_aibom_mcp3 -p no:cacheprovider tests\unit\test_aibom_gateway.py tests\unit\test_upstream_elicitation.py tests\integration\test_mcp_e2e.py tests\test_aibom_bench_supply_chain.py tests\test_pipeline_smoke.py tests\integration\test_proxy_smoke.py tests\unit\test_config.py -x --tb=short`：41 passed；`python -m compileall -q src tests demo`：通过；`git diff --check`：通过，仅 CRLF 提示。
- `python scripts\verify_audit.py --path logs\opencode-smoke\audit.jsonl`：verified 2 records，0 chain/hash errors，0 missing-field records，0 anchor errors。

未完成 / 客观限制：
- 未接真实 marketplace、Trae/Cursor/CodeBuddy/Qoder CN 插件商店或下载执行器；当前只在 XA-Guard 暴露的 MCP `install_plugin` 参数面做离线 preflight。
- 未接实时漏洞/信誉 feed、生产级 TUF/Sigstore/组织签名信任根；离线缓存由服务端运维预置。
- PRD L3 仍未整体完成：真实客户端 HITL UI、外部 TSA/生产国密链、Docker Compose runtime/Linux gVisor、官方外部 benchmark 与交付材料仍待补。

## 2026-06-17 20:06 +08:00 Codex 主 agent（+2 gpt-5.5 medium 子 agent）- L3 HITL pending schema 感知脱敏

本次具体做了什么：
- 继续 L3 目标，派出 2 个 `gpt-5.5 medium` 子 agent 做只读审查：一个审查 schema 感知脱敏实现，一个审查 README/status/log 口径；子 agent 均未直接修改文件。
- 修改 `src/xa_guard/proxy/pending.py`：`redact_arguments()` 支持工具 `inputSchema` 标注，识别 `x-xa-guard-sensitive: true`、`x-sensitive: true`、`writeOnly: true`、`format: password`；支持 object `properties`、array `items` 和 dict 型 `additionalProperties` 的递归脱敏；字段名 best-effort 仍作为 fallback。
- 修改 `src/xa_guard/proxy/upstream.py`：`_build_app()` 建立 `tool_name -> inputSchema` 映射；pending ledger 写盘、pending list 展示和 MCP elicitation message 都使用 schema-aware redaction。schema 标注字段在当前进程内仍可用原始参数 approve 执行；重启后若只剩脱敏参数仍 fail-closed。
- 修改 `configs/xa-guard.docker.yaml`：给 Docker profile 静态 manifest 中 `send_email.to` / `send_email.body` 增加少量敏感标注，作为 L3 schema redaction demo 证据。
- 扩展 `tests/unit/test_pending_ledger.py`：覆盖 `x-xa-guard-sensitive`、`writeOnly`、array items、普通字段不误伤和 ledger 不含 schema 标注字段明文。
- 扩展 `tests/unit/test_upstream_elicitation.py`：覆盖 pending list / ledger 使用工具 schema 脱敏、当前进程 approve 仍使用原始参数、elicitation message 不展示 schema 标注字段明文。
- 更新 `README.md`、`status.md`，明确这是 schema 标注优先、字段名回退的 L3 原型，不是完整 JSON Schema 解释器、完整 DLP 或 KMS 加密恢复。

验证：
- `python -m pytest -q --basetemp pytest_tmp_l3_pending_schema_redaction1 -p no:cacheprovider tests\unit\test_pending_ledger.py tests\unit\test_upstream_elicitation.py tests\integration\test_mcp_e2e.py -x --tb=short`：25 passed。
- `python -m pytest -q --basetemp pytest_tmp_l3_pending_schema_broad1 -p no:cacheprovider tests\unit\test_pending_ledger.py tests\unit\test_upstream_elicitation.py tests\integration\test_mcp_e2e.py tests\test_approval.py tests\test_pipeline_smoke.py tests\integration\test_proxy_smoke.py tests\unit\test_config.py tests\integration\test_l3_compose_config_smoke.py -x --tb=short`：47 passed。
- `python -m compileall -q src tests`：通过。
- `git diff --check`：通过，仅 CRLF 提示。

未完成 / 客观限制：
- schema 支持是常见标注与 properties/items/additionalProperties 递归，不是完整 JSON Schema 求值；未实现 oneOf/anyOf/allOf 的完整合并语义。
- 不识别自由文本中的秘密；没有工具 schema 感知的值级 DLP、数据分类分级策略或人工安全评审。
- 没有 KMS/DPAPI/国密加密恢复；含脱敏参数的 pending 项重启后仍 fail-closed。
- 真实 IDE HITL UI、多实例审批一致性、完整 RBAC、外部 TSA 和 Docker runtime/gVisor 仍未完成。

## 2026-06-17 20:00 +08:00 Codex 主 agent（+2 gpt-5.5 medium 子 agent）- L3 HITL pending ledger 敏感参数脱敏

本次具体做了什么：
- 继续 L3 目标，派出 2 个 `gpt-5.5 medium` 子 agent 做只读审查：一个审查 pending ledger 参数脱敏设计，一个审查 README/status/log 的能力边界；子 agent 均未直接修改文件。
- 修改 `src/xa_guard/proxy/pending.py`：新增递归 `redact_arguments()` / `arguments_are_redacted()`，对常见敏感参数键做 best-effort 脱敏，包括 `password/passwd/pwd`、`token/*_token`、`secret/*_secret`、`api_key/*_key`、`authorization`、`cookie` 等；避免简单 substring 误伤 `monkey` 这类普通字段。
- pending ledger 写入 `context.arguments` 前先脱敏，并额外记录 `arguments_redacted` 与 `arguments_sha256`；metadata 脱敏仍过滤 token 类字段。
- 修改 `src/xa_guard/proxy/upstream.py`：`xa_guard_list_pending_approvals` 返回脱敏参数；若重启后 pending 只能从 ledger 恢复到脱敏参数，approve 会 fail-closed，不调用下游，并通过 `pipeline.reject_after_approval()` 追加 `deny` 审计，理由为 `pending_arguments_redacted_after_restart`。
- 当前进程内未重启的 pending 项仍保留内存原始参数，operator approve 后可正常执行；ledger 和 list 不暴露敏感明文。
- 扩展 `tests/unit/test_pending_ledger.py`、`tests/unit/test_upstream_elicitation.py`、`tests/integration/test_mcp_e2e.py`：覆盖递归脱敏、普通字段不误伤、ledger/list 无敏感明文、重启后敏感参数 approve fail-closed、审计链 `require_approval -> deny`。
- 更新 `README.md`、`status.md`，明确这是字段名驱动的本地 ledger 明文收敛原型，不是完整 DLP、KMS 加密恢复或生产级隐私合规。

验证：
- `python -m pytest -q --basetemp pytest_tmp_l3_pending_redaction2 -p no:cacheprovider tests\unit\test_pending_ledger.py tests\unit\test_upstream_elicitation.py tests\integration\test_mcp_e2e.py -x --tb=short`：22 passed。
- `python -m pytest -q --basetemp pytest_tmp_l3_pending_redaction3 -p no:cacheprovider tests\unit\test_pending_ledger.py tests\unit\test_upstream_elicitation.py tests\integration\test_mcp_e2e.py -x --tb=short`：22 passed。
- `python -m compileall -q src tests`：通过。
- `python -m pytest -q --basetemp pytest_tmp_l3_pending_redaction_broad1 -p no:cacheprovider tests\unit\test_pending_ledger.py tests\unit\test_upstream_elicitation.py tests\integration\test_mcp_e2e.py tests\test_approval.py tests\test_pipeline_smoke.py tests\integration\test_proxy_smoke.py tests\unit\test_config.py -x --tb=short`：43 passed。
- `git diff --check`：通过，仅 CRLF 提示。

未完成 / 客观限制：
- 脱敏是字段名驱动 best-effort，不是完整 DLP；不识别自由文本中的秘密，也没有按工具 schema / 数据分类分级做精细策略。
- 为避免伪加密，当前没有把敏感原文加密落盘；因此含敏感键的 pending 项在服务重启后不能自动恢复执行，只能 fail-closed 并要求重新发起。
- 没有接 KMS/DPAPI/国密密钥管理、外部审批系统、多实例一致性、完整 RBAC 或真实 IDE HITL UI。

## 2026-06-17 19:52 +08:00 Codex 主 agent（+2 gpt-5.5 medium 子 agent）- L3 HITL pending 本地 ledger / 重启恢复

本次具体做了什么：
- 继续 L3 目标，派出 2 个 `gpt-5.5 medium` 子 agent 做只读审查：一个审查 pending approval 持久化设计，一个审查 README/status/log 的 L3 表述边界；子 agent 均未直接修改文件。
- 新增 `src/xa_guard/proxy/pending.py`：实现 `PendingApprovalStore`，支持可选本地 JSONL ledger；记录 `pending_added` / `pending_removed` 生命周期事件，启动时重放 ledger 恢复未过期 pending 项，`list/pop/add` 时清理过期项。
- pending ledger 只保存恢复审批所需的 `GateContext` 快照：trace/span、tool/arguments、role、input sources、taint/risk、gate_results、rule_hits、final_decision/final_reason；不保存 approval token、operator token、approval secret 或工具执行结果。
- 修改 `src/xa_guard/proxy/upstream.py`：用新的 `PendingApprovalStore` 替换进程内 dict；支持 `XA_GUARD_PENDING_APPROVAL_STORE` 环境变量覆盖 ledger 路径，或从配置项 `pending_approvals_path` 读取。
- 修改 `src/xa_guard/config.py`、`configs/xa-guard.yaml`、`configs/xa-guard.docker.yaml`：增加 `pending_approvals_path`，默认指向 `./logs/runtime/pending_approvals.jsonl`。
- 新增 `tests/unit/test_pending_ledger.py`：覆盖 ledger 上下文恢复、token 字段脱敏、pop 生命周期记录和 TTL 过期清理。
- 扩展 `tests/unit/test_upstream_elicitation.py`：覆盖 app 重建后从 ledger list/approve/reject pending，approval token 不落 ledger。
- 扩展 `tests/integration/test_mcp_e2e.py`：新增 MCP E2E 重启恢复场景，同一 ledger 路径下第二个 app 恢复 pending 并 approve，审计链仍为 `require_approval -> allow`。
- 更新 `README.md`、`status.md`，明确这是单机本地 ledger 原型，不是生产级审批系统、多实例一致性、完整 RBAC、真实 IDE 弹窗或外部可信 TSA。

验证：
- `python -m pytest -q --basetemp pytest_tmp_l3_pending_ledger1 -p no:cacheprovider tests\unit\test_pending_ledger.py tests\unit\test_upstream_elicitation.py -x --tb=short`：15 passed。
- `python -m compileall -q src tests`：通过。
- `python -m pytest -q --basetemp pytest_tmp_l3_pending_ledger_e2e1 -p no:cacheprovider tests\unit\test_pending_ledger.py tests\unit\test_upstream_elicitation.py tests\integration\test_mcp_e2e.py -x --tb=short`：17 passed。
- `python -m pytest -q --basetemp pytest_tmp_l3_pending_ledger_broad1 -p no:cacheprovider tests\unit\test_pending_ledger.py tests\unit\test_upstream_elicitation.py tests\integration\test_mcp_e2e.py tests\test_approval.py tests\test_pipeline_smoke.py tests\integration\test_proxy_smoke.py tests\unit\test_config.py -x --tb=short`：38 passed。
- `git diff --check`：通过，仅 CRLF 提示。

未完成 / 客观限制：
- JSONL ledger 是单机本地恢复原型；没有文件锁、分布式一致性、多 worker 协调或外部审批系统。
- pending arguments 当前按原始参数落本地 ledger，尚未做字段级脱敏策略；生产环境需要按工具 schema/数据密级脱敏。
- approval token 仍是进程内 one-shot 消费表，多实例/重启后的全局防重放需要共享 nonce registry。
- 真实 Trae / 国产 IDE HITL UI 截图、完整 RBAC、外部可信 TSA/国密签名和 Docker Compose runtime 验收仍未完成。

## 2026-06-17 19:43 +08:00 Codex 主 agent（子 agent 尝试受额度限制）- L3 Docker Compose 部署 verifier

本次具体做了什么：
- 继续 L3 目标，沿用此前 Russell 子 agent 对 deployment verifier 的只读审查建议；本轮再次尝试派出 2 个 `gpt-5.5 medium` 子 agent 审查部署 verifier 与文档口径，但两个子 agent 均因额度限制报错，未修改文件、未产出可用审查结论。
- 新增 `scripts/verify_l3_deployment.py`：默认安全模式只检查部署文件清单/hash、Docker daemon 状态、`docker compose config` 与静态 Compose/config 摘要；只有显式传入 `--run-build` / `--run-up` 才执行镜像构建、启动 `xa-guard` 服务和 `/healthz` 检查。
- verifier 输出 `xa-l3-deployment-verification/v0.1` JSON，包含 compose/config/Dockerfile hash、Streamable HTTP transport、Gate5 `sandbox_all_tools`、sandbox 镜像、Docker socket mount、healthcheck、步骤状态和 limitations。
- 将 Docker daemon / Docker Desktop 未启动识别为 `blocked_external_dependency`，避免把外部环境未就绪误记成产品配置失败；脚本仅在 `summary.status=pass` 时退出 0。
- 新增 `tests/unit/test_l3_deployment_verifier.py`，覆盖 Docker daemon 缺失、显式 build/up 成功路径，以及显式 build/up 但 Docker daemon 缺失时 runtime 步骤标记为 blocked。
- 更新 `README.md`、`status.md`，说明默认诊断不会启动容器，完整 build/up 需要本机 Docker daemon 可用。

验证：
- `python -m pytest -q --basetemp pytest_tmp_l3_deploy_verify4 -p no:cacheprovider tests\unit\test_l3_deployment_verifier.py -x --tb=short`：3 passed。
- `python scripts\verify_l3_deployment.py --output pytest_tmp_l3_deployment_verification4.json`：生成报告；文件/hash、静态摘要和 `docker compose config` 通过，但 `docker_version` 因 Docker Desktop daemon 未启动（`dockerDesktopLinuxEngine` pipe 不存在）标记为 `blocked_external_dependency`。
- `python -m pytest -q --basetemp pytest_tmp_l3_deploy_broad4 -p no:cacheprovider tests\unit\test_l3_deployment_verifier.py tests\integration\test_l3_compose_config_smoke.py tests\unit\test_config.py tests\unit\test_downstream_sandbox.py tests\unit\test_gate5.py tests\integration\test_proxy_smoke.py -x --tb=short`：23 passed。
- `python -m compileall -q scripts src tests`：通过。
- `git diff --check`：通过，仅 CRLF 提示。

未完成 / 客观限制：
- 当前机器 Docker Desktop daemon 未启动，`docker compose build/up` 与服务 `/healthz` 的真实 runtime 验收仍未完成。
- verifier 是部署证据收集器，不替代 Linux/gVisor 真实运行、国产 IDE 真实 HITL 截图、外部 TSA 或长期运行压测。
- 两个新子 agent 因额度限制未能协助；本轮有效子 agent 输入来自此前 Russell 的只读部署审查。

## 2026-06-17 14:55 +08:00 Codex 主 agent（+2 gpt-5.5 medium 子 agent）- L3 外部 benchmark 本地 projection 证据

本次具体做了什么：
- 继续 L3 目标，派出 2 个 `gpt-5.5 medium` 子 agent 只读审查 external archive 的 projection 设计、安全边界和测试点；子 agent 均未直接修改文件。
- 修改 `bench/external/schema.py`：`xa_guard_projection.input_payload` 优先从外部记录的首个 `tool_calls/actions` 中提取 `tool_name` 与 `arguments`，减少全部落到 `external_benchmark_case` 的无效投影。
- 新增 `bench/external/projection.py`：把 normalized records 的 `xa_guard_projection.input_payload` 送入本地 XA-Guard pipeline，用 mock executor 运行 Gate1–Gate6，生成本地 projection decisions；隔离 audit 输出到 archive 内部目录，不写默认 `logs/audit`。
- 扩展 `bench/external/cli.py archive --run-projection`：启用后生成 `xa-guard-projection/results.json`、`summary.json`、`audit/audit.jsonl`、`audit-verify.json`；manifest 记录 projection claim_scope、非官方声明、results/summary/audit hash、audit 验链摘要、config path/hash。
- projection summary 使用 `xa_guard_projection_*` 字段名，避免裸 `ASR` / `score` / leaderboard 口径；不回写 normalized record 的 `observed` 或 smoke metrics。
- 扩展 `tests/unit/test_external_benchmarks.py`：覆盖 `archive --run-projection` 的本地证据语义、隔离 audit、manifest projection 字段、summary 非官方声明、projection 不污染 smoke metrics、audit verify 记录数与 hash。
- 更新 `README.md`、`docs/external-benchmarks.md`、`status.md`，明确 `--run-projection` 是本地 XA-Guard 防护投影，不是 AgentDojo/InjecAgent 官方成绩。

验证：
- `python -m pytest -q --basetemp pytest_tmp_l3_external_projection2 -p no:cacheprovider tests\unit\test_external_benchmarks.py -x --tb=short`：6 passed。
- `python -m bench.external.cli archive --benchmark agentdojo --input bench/external/fixtures/agentdojo_smoke.jsonl --out-dir pytest_tmp_external_projection_smoke2\agentdojo --run-projection --config configs/xa-guard.yaml`：成功生成 projection results/summary/audit/audit-verify。
- `python -m pytest -q --basetemp pytest_tmp_l3_external_projection_broad -p no:cacheprovider tests\unit\test_external_benchmarks.py tests\unit\test_opa_export.py tests\integration\test_l3_compose_config_smoke.py tests\unit\test_downstream_sandbox.py tests\integration\test_mcp_e2e.py tests\test_approval.py tests\test_pipeline_smoke.py -x --tb=short`：33 passed。
- `python -m compileall -q bench src tests`：通过。

未完成 / 客观限制：
- projection 是本地 XA-Guard pipeline + mock executor 防护模拟，不能作为官方 AgentDojo/InjecAgent ASR、Utility、leaderboard score。
- projection 质量依赖 normalizer 对外部 tool call 的 best-effort 映射；真实官方环境、模型执行、数据许可和上游 commit 仍未接入。
- projection audit 已隔离并验链，但还没有外部 TSA/国密签名，也没有统一 evidence/ 顶层真实归档。

## 2026-06-17 14:45 +08:00 Codex 主 agent（+2 gpt-5.5 medium 子 agent）- L3 外部 benchmark evidence archive

本次具体做了什么：
- 继续 L3 目标，派出 2 个 `gpt-5.5 medium` 子 agent 只读审查外部 benchmark adapter 与证据交付结构；子 agent 均未直接修改文件。
- 新增 `bench/external/report.py`：从 normalized external benchmark JSONL 构造非官方 report，包含 input hash、validation error、benchmark/suite 分布、标签覆盖、smoke metrics、limitation counts、推荐归档字段。
- 扩展 `bench/external/cli.py`：
  - `normalize` 输出增强为评审友好的 JSON，包含 benchmark、claim_scope、schema/adaptor 版本、input/output sha256、输入字节数、records_read/written、limitations。
  - `validate` 输出增强为包含 input sha256、schema version、records_valid、errors_count 的结构化 JSON。
  - `smoke-metrics` 输出增强为 `metric_scope=adapter_health_only`、`not_official_benchmark_score=true`，并写明不是 AgentDojo/InjecAgent 官方 ASR。
  - 新增 `report` 子命令，可对 normalized JSONL 输出 `report.json`。
  - 新增 `archive` 子命令：一次性生成 `normalized.jsonl`、`validation.json`、`smoke-metrics.json`、`report.json`、`manifest.json`、`README.md`；manifest 记录 input/normalized/schema hash、adapter/schema 版本、validation counts、limitations 和 `official_claim=false`。
- 扩展 `tests/unit/test_external_benchmarks.py`：覆盖 AgentDojo archive 目录完整性、manifest hash 正确性、`official_claim=false`、InjecAgent archive smoke。
- 更新 `README.md`、`docs/external-benchmarks.md`、`status.md`、`bench/.log/worklog.md`，明确 external archive 是 supporting evidence，不是官方 benchmark 成绩。

验证：
- `python -m bench.external.cli archive --benchmark agentdojo --input bench/external/fixtures/agentdojo_smoke.jsonl --out-dir pytest_tmp_external_archive_smoke\agentdojo`：成功生成 manifest/report/normalized/validation/smoke-metrics/README。
- `python -m pytest -q --basetemp pytest_tmp_l3_external_archive -p no:cacheprovider tests\unit\test_external_benchmarks.py -x --tb=short`：5 passed。
- `python -m pytest -q --basetemp pytest_tmp_l3_external_archive_broad -p no:cacheprovider tests\unit\test_external_benchmarks.py tests\unit\test_opa_export.py tests\integration\test_l3_compose_config_smoke.py tests\unit\test_downstream_sandbox.py tests\integration\test_mcp_e2e.py tests\test_approval.py -x --tb=short`：27 passed。
- `python -m compileall -q bench src tests`：通过。

未完成 / 客观限制：
- `archive` 仍只归档用户提供/fixture 导出，不下载或运行官方 AgentDojo/InjecAgent 环境，不产生官方可比 ASR/Utility。
- Python 校验仍以现有轻量 `validate_record()` 为主，尚未接完整 JSON Schema engine。
- 尚未实现 `--run-projection` 将 `xa_guard_projection` 送入 XA-Guard pipeline 并把决策/审计 hash 写入 archive。
- 长期 evidence 目录结构与真实上游 source commit/license/transcript 仍需在拿到官方导出和实际环境后补齐。

## 2026-06-17 14:37 +08:00 Codex 主 agent（+2 gpt-5.5 medium 子 agent）- L3 HITL 审批证据链加固

本次具体做了什么：
- 继续 L3 目标，派出 2 个 `gpt-5.5 medium` 子 agent 只读审查：一个复核 L3 全局缺口与下一步优先级，一个专门审查 HITL / approval / audit 生产语义。子 agent 均未直接修改文件。
- 根据审查结论继续加固 HITL fallback，不把上一轮 pending approval 当作完成状态。
- 在 `src/xa_guard/approval.py` 新增 `verify_and_consume_approval()`：在原有 HMAC 验签、args_hash、防过期基础上，加入进程内 token 消费表。同一 approval token 在当前进程内只能通过一次，第二次会返回 `approval_token_replay`。
- 修改 `src/xa_guard/pipeline.py`：`run_after_approval()` 改用 `verify_and_consume_approval()`，让 approval token 从“TTL 内可复用凭据”变为 L3 原型级 one-shot capability；新增 `reject_after_approval()`，用于在原 `require_approval` 审计之后追加一条 `deny` 审计，记录人工拒绝的 approver/reason。
- 修改 `src/xa_guard/proxy/upstream.py`：elicitation reject 与 pending reject 都调用 `pipeline.reject_after_approval()`，不触达下游但会写第二条 deny 审计；`XA_GUARD_APPROVAL_OPERATOR_TOKEN` 配置后，`xa_guard_list_pending_approvals`、approve、reject 都必须传入匹配 `operator_token`。
- 更新 `tests/test_approval.py`：覆盖 `verify_and_consume_approval()` 防重放、pipeline 级 approval token replay 拒绝且下游只执行一次。
- 更新 `tests/unit/test_upstream_elicitation.py`：覆盖 list/approve/reject operator token 校验，fake pipeline 增加 reject 审计接口。
- 更新 `tests/integration/test_mcp_e2e.py`：reject 路径从原来的单条 `require_approval` 审计升级为 `require_approval -> deny`，断言 deny 行含 final_reason、approver 且无 approval_token；整体审计链长度随之更新。
- 更新 `README.md`、`status.md`、`src/xa_guard/proxy/.log/worklog.md`，明确当前能力：pending approve one-shot、reject 可追溯、operator token 覆盖 list/approve/reject；仍不是完整持久化审批系统/RBAC。

验证：
- `python -m pytest -q --basetemp pytest_tmp_l3_hitl_reject_replay2 -p no:cacheprovider tests\test_approval.py tests\test_pipeline_smoke.py tests\unit\test_upstream_elicitation.py tests\integration\test_mcp_e2e.py -x --tb=short`：27 passed。
- `python -m compileall -q src tests`：通过。
- `python -m pytest -q --basetemp pytest_tmp_l3_hitl_broad -p no:cacheprovider tests\test_approval.py tests\test_pipeline_smoke.py tests\unit\test_upstream_elicitation.py tests\integration\test_mcp_e2e.py tests\integration\test_proxy_smoke.py tests\integration\test_l3_compose_config_smoke.py tests\unit\test_config.py tests\unit\test_downstream_sandbox.py tests\unit\test_gate5.py tests\unit\test_opa_export.py tests\unit\test_gate3.py::test_rego_backend_uses_layered_merged_view tests\test_sdk_protect.py tests\test_langchain_integration.py -x --tb=short`：55 passed，1 skip（当前环境未安装 `langchain_core`）。

未完成 / 客观限制：
- approval token 防重放目前是进程内内存表，服务重启或多实例部署后不能提供全局 one-shot；生产级需要外部审批/审计存储或共享 nonce registry。
- pending store 仍是进程内内存态，尚不支持重启恢复、多 worker 协调或持久化 pending ledger。
- operator token 仍是 demo 级 bearer token，不是完整 RBAC；真实生产还需要 operator 身份、角色、审批范围、list 参数脱敏和操作审计。
- 真实 Trae / 国产 IDE HITL 证据、Docker Compose 实际 build/up、外部 AgentDojo/InjecAgent/TSA 仍未完成。

## 2026-06-17 09:44 +08:00 Codex 主 agent（+2 gpt-5.5 medium 子 agent）- L3 HITL pending approval fallback

本次具体做了什么：
- 继续 L3 目标，按用户要求沿用并等待 2 个 `gpt-5.5 medium` 子 agent 只读分析：一个审查 upstream/pipeline pending approval 设计，一个审查测试与审计闭环风险。子 agent 均未直接修改文件。
- 在 `src/xa_guard/proxy/upstream.py` 新增内存 pending approval store。红色工具触发 `REQUIRE_APPROVAL` 后，若当前 MCP 客户端没有 elicitation 通道或 elicitation 不可用，不再回落为普通拦截文本，而是保存原始 `GateContext`，返回 `trace_id`、过期时间和审批工具提示。
- 新增两个上游内置控制工具：`xa_guard_list_pending_approvals` 与 `xa_guard_approve_pending`。这两个工具在 `call_tool()` 开头本地短路处理，不进入 downstream，也不走普通 pipeline，避免审批工具被策略误伤或递归。
- `xa_guard_approve_pending` 批准时复用原始 ctx，调用现有 `issue_approval()` 签发 HMAC approval token，再调用 `pipeline.run_after_approval()` 完成验签、审计和下游执行；pending 项 approve/reject 后即删除，重复批准会返回“不存在或已过期”，避免同一 pending 请求被二次执行。若设置 `XA_GUARD_APPROVAL_OPERATOR_TOKEN`，审批工具会强制校验传入的 `operator_token`，错误 token 不消费 pending。
- 拒绝 pending approval 时不触达下游，保持与现有 elicitation reject 一致的最小审计语义：已有第一条 `require_approval` 审计，不额外写 reject 记录。
- 扩展 MCP E2E fixture：新增 `pending_approval_op` 红色测试工具，并在 `policies/baseline/gate4_capabilities.yaml` 和 legacy `gate2_tool_risks.yaml` 登记，确保 layered 与 legacy Gate2 路径都将其判定为 RED。
- 扩展 `tests/unit/test_upstream_elicitation.py`：覆盖无 elicitation 时 pending、list、approve、reject、一次性消费、operator token 校验和审批 token 字段。
- 扩展 `tests/integration/test_mcp_e2e.py`：真实 MCP memory transport 下验证 pending fallback 跨 client session 可 list/approve，批准后仅执行一次，审计为 `require_approval -> allow` 且 trace/参数/approval args_hash 闭环一致。
- 更新 `README.md`、`status.md`、`src/xa_guard/proxy/.log/worklog.md`，客观标明 pending approval 是无 elicitation 客户端的 L3 原型 fallback，真实 Trae / 国产 IDE 弹窗截图仍未完成。

验证：
- `python -m pytest -q --basetemp pytest_tmp_l3_pending -p no:cacheprovider tests\unit\test_upstream_elicitation.py tests\integration\test_mcp_e2e.py -x --tb=short`：10 passed。
- `python -m pytest -q --basetemp pytest_tmp_l3_pending_policy2 -p no:cacheprovider tests\unit\test_upstream_elicitation.py tests\integration\test_mcp_e2e.py tests\unit\test_gate2.py tests\test_tool_gate_coverage_matrix.py -x --tb=short`：30 passed。
- `python -m compileall -q src tests`：通过。
- `python -m pytest -q --basetemp pytest_tmp_l3_pending_broad2 -p no:cacheprovider tests\unit\test_upstream_elicitation.py tests\integration\test_mcp_e2e.py tests\integration\test_proxy_smoke.py tests\integration\test_l3_compose_config_smoke.py tests\unit\test_config.py tests\unit\test_downstream_sandbox.py tests\unit\test_gate5.py tests\unit\test_opa_export.py tests\unit\test_gate3.py::test_rego_backend_uses_layered_merged_view tests\test_sdk_protect.py tests\test_langchain_integration.py -x --tb=short`：39 passed，1 skip（当前环境未安装 `langchain_core`）。

未完成 / 客观限制：
- pending approval 当前是进程内内存态，服务重启后丢失；尚未接外部审批系统、operator token/RBAC、持久化队列或多实例协调。
- pending reject 当前不追加第二条 deny 审计，语义与现有 elicitation reject 保持一致；如后续要做完整人工拒绝审计，需要在 `Pipeline` 增加显式 reject-after-approval 流程。
- 真实 Trae / 国产 IDE HITL 弹窗、截图和多客户端交互证据仍未完成；本次只完成协议内 fallback 和进程内 E2E。

## 2026-06-17 09:30 +08:00 Codex 主 agent（+3 gpt-5.5 medium 子 agent）- L3 审计锚定与 Compose/Gate5 闭环增量

本次具体做了什么：
- 继续 L3 目标，沿用并等待 3 个 `gpt-5.5 medium` 子 agent 的只读分析：外部 AgentDojo/InjecAgent benchmark、Compose/Gate5 闭环、审计证据链。子 agent 均未直接改文件。
- 新增 `src/xa_guard/audit/tsa.py`：提供本地文件 TSA anchor 原型。anchor manifest 覆盖 audit 文件 SHA-256、字节数、记录数、首条/末条 `record_hash`、hash 算法、生成时间，并写 `anchors/index.jsonl` 串联多次 anchor 的 `previous_anchor_hash`。
- 新增 `scripts/anchor_audit.py`，增强 `scripts/verify_audit.py`：验证脚本不再只看 `hash_prev`，而是复用 `verify_audit_jsonl()` 重算每行 `record_hash`；支持 `--anchor` 和 `--verify-anchor-index`。
- 新增 `tests/unit/test_audit_tsa.py`，覆盖 anchor 创建、验锚、审计篡改拒绝、旧 anchor 失效、index 串联。
- 加固 Docker Compose/Gate5 原型：`docker-compose.yml` 默认构建 `sandbox-image`；`docker/xa-guard.Dockerfile` 安装 Docker CLI；`docker/sandbox.Dockerfile` 内置 `src/`、`demo/` 和项目依赖；`configs/xa-guard.docker.yaml` 将 `workspace_mount` 改为 `false`，避免 Docker-outside-of-Docker 路径错绑。
- 新增 sandbox policy 单测，确认 `workspace_mount=false` 时 Docker 命令不绑定宿主目录。
- 继续补 L3 工具发现闭环：`DownstreamSpec.tools` 支持静态工具 manifest；docker profile 在 `configs/xa-guard.docker.yaml` 内声明 ops_target 工具清单，`DownstreamRouter.start()` 不再裸启动 stdio downstream 做 `list_tools`；`gate5.sandbox_all_tools=true` 让 docker profile 下 GREEN 工具调用也至少走 Docker sandbox。
- 新增 `tests/integration/test_l3_compose_config_smoke.py` 和相关单测，锁住 docker profile 静态 discovery 不创建原生 session。
- 新增 `bench.external` adapter skeleton：支持 AgentDojo/InjecAgent 用户导出 JSON/JSONL/CSV 的离线 normalize、validate、smoke-metrics；输出统一 JSONL，并强制 `official_claim=false` / `not_official_reproduction`。
- 新增 `docs/external-benchmarks.md`、`bench/schema/external-benchmark-result.schema.json`、synthetic smoke fixtures 和 `tests/unit/test_external_benchmarks.py`；不下载官方数据、不运行官方环境、不声明官方成绩。
- 新增 OPA/Rego merged-view 原型：`src/xa_guard/policy/opa_export.py`、`scripts/export_opa_policy.py`；导出当前 `LayeredPolicySource` 的 `data.json`、`gate3.rego`、`manifest.json`。
- 修改 Gate3：`backend=rego + prefer_layered=true` 时按 `LayeredPolicySource.bundle_sha` 构建/缓存 merged rules 的 `RegoPolicyEngine`，overlay 热加载后 bundle_sha 变化会触发重建；无 OPA binary 时仍走现有 Python fallback。
- 抽出 SDK `preflight_tool_call()` helper，并新增 `xa_guard.integrations.langchain.protect_tool()`：包装单个 LangChain `BaseTool` 的 `_run/_arun`，DENY/REQUIRE_APPROVAL 时抛 `XAGuardBlocked` 且不调用原工具。当前环境未安装 langchain-core，集成测试按可选依赖 skip。
- 更新 `README.md`、`status.md`、模块工作日志，客观标明：本地文件 anchor 不是外部生产 TSA，Compose 实际 build/up 因 Docker daemon 未启动仍未验收。

验证：
- `python -m pytest -q --basetemp pytest_tmp_l3_tsa2 -p no:cacheprovider tests\unit\test_audit_tsa.py tests\unit\test_merkle.py tests\unit\test_audit_archive.py -x --tb=short`：11 passed。
- `python -m pytest -q --basetemp pytest_tmp_l3_sandbox -p no:cacheprovider tests\unit\test_sandbox_policy.py tests\unit\test_downstream_sandbox.py tests\unit\test_gate5.py -x --tb=short`：13 passed。
- `python -m compileall -q src scripts tests`：通过。
- CLI smoke：生成临时 audit JSONL，`scripts/anchor_audit.py` 成功写 anchor/index，`scripts/verify_audit.py --anchor --verify-anchor-index` 通过。
- `docker compose config`：通过。
- `docker compose build sandbox-image`：未执行成功，原因是本机 Docker Desktop daemon 未启动，报 `dockerDesktopLinuxEngine` pipe 不存在。
- `python -m pytest -q --basetemp pytest_tmp_l3_final_full -p no:cacheprovider -x --tb=short`：全量代码回归通过，但 `tests/integration/test_sandbox_runner.py` 因本地 `xa-guard/sandbox:latest` 镜像不可用 skip 1 条；该现象与 Docker daemon 未启动一致。
- `python -m pytest -q --basetemp pytest_tmp_l3_discovery -p no:cacheprovider tests\unit\test_config.py tests\unit\test_gate5.py tests\unit\test_downstream_sandbox.py tests\integration\test_proxy_smoke.py tests\integration\test_l3_compose_config_smoke.py -x --tb=short`：20 passed。
- `python -m pytest -q --basetemp pytest_tmp_l3_external -p no:cacheprovider tests\unit\test_external_benchmarks.py tests\unit\test_config.py tests\unit\test_gate5.py tests\unit\test_downstream_sandbox.py tests\integration\test_l3_compose_config_smoke.py -x --tb=short`：21 passed。
- `python -m bench.external.cli normalize/validate/smoke-metrics` 对 InjecAgent synthetic fixture smoke 通过。
- `python -m compileall -q bench src tests`：通过。
- `python -m pytest -q --basetemp pytest_tmp_l3_round2_targeted -p no:cacheprovider tests\unit\test_external_benchmarks.py tests\unit\test_config.py tests\unit\test_gate5.py tests\unit\test_downstream_sandbox.py tests\integration\test_l3_compose_config_smoke.py tests\integration\test_proxy_smoke.py tests\integration\test_mcp_e2e.py -x --tb=short`：24 passed。
- `python -m pytest -q --basetemp pytest_tmp_l3_round2_full -p no:cacheprovider -x --tb=short`：全量代码回归通过，仍有 1 条 `test_sandbox_runner.py` 因本地 `xa-guard/sandbox:latest` 镜像不可用 skip。
- `python -m pytest -q --basetemp pytest_tmp_l3_opa -p no:cacheprovider tests\unit\test_opa_export.py tests\unit\test_gate3.py::test_rego_backend_uses_layered_merged_view tests\unit\test_gate3.py::test_rego_backend_evaluates_with_python_fallback tests\unit\test_gate3.py::test_rego_transpiler_covers_current_dsl_shapes tests\unit\test_layered_policy.py -x --tb=short`：39 passed。
- `python scripts\export_opa_policy.py --out-dir pytest_tmp_l3_opa_cli\opa-bundle`：成功导出 OPA bundle manifest，当前 baseline merged_rules=31、tool_caps=48、sensitive_patterns=29。
- `python -m pytest -q --basetemp pytest_tmp_l3_opa_sdk -p no:cacheprovider tests\unit\test_opa_export.py tests\unit\test_gate3.py::test_rego_backend_uses_layered_merged_view tests\test_sdk_protect.py tests\test_langchain_integration.py -x --tb=short`：通过；`test_langchain_integration.py` 因当前环境未安装 `langchain_core` skip 1 条。
- `python -m pytest -q --basetemp pytest_tmp_l3_round3_targeted -p no:cacheprovider tests\unit\test_opa_export.py tests\unit\test_gate3.py::test_rego_backend_uses_layered_merged_view tests\unit\test_layered_policy.py tests\test_sdk_protect.py tests\test_langchain_integration.py tests\unit\test_external_benchmarks.py tests\integration\test_l3_compose_config_smoke.py tests\unit\test_downstream_sandbox.py -x --tb=short`：靶向通过；因未安装 `langchain_core` skip 1 条。
- `python -m pytest -q --basetemp pytest_tmp_l3_round3_full -p no:cacheprovider -x --tb=short`：全量代码回归通过；skip 2 条，分别是本地 `xa-guard/sandbox:latest` 镜像不可用、当前环境未安装 `langchain_core`。

未完成 / 客观限制：
- 本地文件 TSA anchor 是可审计 demo/CI 证据锚，不是第三方可信时间戳服务；生产级 SM2/SM3 密钥管理、外部 TSA、签名并发写入的原子化仍未完成。
- Compose 配置已更接近一键闭环，但完整 `docker compose up --build -d`、容器内 MCP `list_tools` + 高风险工具调用、长期运行和 Linux/gVisor/runsc 仍未实测。
- docker profile 的下游工具发现已静态化；普通本地 stdio 配置仍保留动态 discovery，主要用于开发/测试。
- AgentDojo/InjecAgent 当前只有 adapter skeleton；现有 XA-Bench 290 指标和 adapter smoke metrics 都不能冒充外部 benchmark 官方 ASR。
- OPA 当前是 merged-view Rego engine/export 原型；真实 OPA CLI 执行、服务化部署、性能和三层包硬化仍未完成。
- LangChain 当前只承诺单个 `BaseTool` wrapper 的强阻断语义；CallbackHandler、HITL approval resume、Agent/LangGraph 全链路 session_history 仍未完成。

## 2026-06-16 21:50 +08:00 Codex 主 agent（+3 gpt-5.5 medium 子 agent）- L3 SDK 非透传 preflight

本次具体做了什么：
- 继续沿 L3 目标推进，派出 3 个 `gpt-5.5 medium` 子 agent 只读分析：SDK/LangChain、Compose 验收、国密/TSA 审计。
- 新增可打包 SDK 命名空间 `src/xa_guard/sdk/`，并从 `xa_guard.__init__` 导出 `protect` / `XAGuardBlocked`；历史顶层 `sdk/` 改为兼容转发。
- 实现 `@protect` 最小非透传能力：同步/异步函数调用前构造 `GateContext`，跑 `build_pipeline()` preflight；若结果为 DENY 或 REQUIRE_APPROVAL，抛出 `XAGuardBlocked`，原函数不会被调用。
- 新增 `tests/test_sdk_protect.py`，覆盖 public imports、绿色工具放行并调用原函数、危险工具阻断且不调用原函数、async 工具放行。
- 更新 `README.md`、`status.md` 和 `sdk/.log/worklog.md`：SDK 不再是纯骨架，但完整 LangChain Callback/Tool wrapper、approval_handler 仍未完成。

验证：
- `python -m pytest -q --basetemp pytest_tmp_l3_sdk -p no:cacheprovider tests\test_sdk_protect.py -x --tb=short`：4 passed。
- `python -m pytest -q --basetemp pytest_tmp_l3_targeted2 -p no:cacheprovider tests\test_sdk_protect.py tests\test_aibom_bench_supply_chain.py tests\unit\test_aibom_gateway.py tests\test_gate1_evaluator.py tests\integration\test_bench_smoke.py -x --tb=short`：21 passed。
- `python -m pytest -q --basetemp pytest_tmp_l3_full_sdk -p no:cacheprovider -x --tb=short`：全量通过，进度 100%，无失败。
- `python -m compileall -q src sdk tests\test_sdk_protect.py`：通过。

未完成 / 客观限制：
- 当前 SDK 是 preflight wrapper，不是完整 LangChain CallbackHandler；LangChain tool wrapper、版本兼容、审批处理和会话上下文采集仍是 L3 后续。
- SDK preflight 写审计的是 guard 检查结果，不是被包装函数的真实返回值审计；这点后续需要在 full wrapper 中补齐。

## 2026-06-16 21:34 +08:00 Codex 主 agent（+4 gpt-5.5 medium 子 agent）- L3 原型地基：Compose、Streamable HTTP、AIBOM bench gateway

本次具体做了什么：
- 按用户要求派出 4 个 `gpt-5.5 medium` 子 agent 并行只读分析：L3 需求映射、部署/沙箱、HITL/MCP/SDK、bench/供应链/评测；子 agent 均未直接改文件。
- 新增 L3 部署原型：`.dockerignore`、`docker/xa-guard.Dockerfile`、`docker-compose.yml`、`configs/xa-guard.docker.yaml`。Compose profile 暴露 Streamable HTTP 端口 3000，挂载 configs/policies/logs，并提供可选 `build-sandbox` profile 构建 `xa-guard/sandbox:latest`。
- 实现 `src/xa_guard/proxy/upstream.py::run_streamable_http()`：使用 MCP `StreamableHTTPServerTransport` + Starlette/uvicorn，新增 `/healthz`；修正 DNS rebinding allowed_hosts 带端口校验。
- 更新 `pyproject.toml`：新增 `http` optional extra（starlette/uvicorn），`all` extra 纳入 http。
- 新增 `xa_guard.aibom.gateway.admit_install_request()`，把 bench/MCP 风格 `install_plugin` 请求转换为 `ScanReport` 后走统一 `admit()` 准入管线。
- 修改 `bench/runner.py`：supply_chain/install_plugin 不再绕旧 `rate_install_request`，改为调用 `admit_install_request()`；结果保留 `aibom_gateway` gate metadata 和 `AIBOM-GATEWAY` rule hit。
- 更新 `README.md`：补 Docker Compose 一键部署说明、Streamable HTTP 当前状态、AIBOM bench gateway 状态，并修正 290 条 seed 维度数量。
- 更新 `status.md`：把仓库状态从“L3 未达”改为“L3 原型推进中”，明确 Compose/HTTP/AIBOM bench 已补，但国密 TSA、真实 Trae HITL、AgentDojo/InjecAgent、500+ 题库、gVisor Linux、LangChain 非透传仍未完成。

验证：
- `python -m pytest -q --basetemp pytest_tmp_l3_aibom -p no:cacheprovider tests\test_aibom_bench_supply_chain.py tests\unit\test_aibom_gateway.py -x --tb=short`：8 passed。
- `python -m pytest -q --basetemp pytest_tmp_l3_targeted -p no:cacheprovider tests\test_aibom_bench_supply_chain.py tests\unit\test_aibom_gateway.py tests\test_gate1_evaluator.py tests\integration\test_bench_smoke.py -x --tb=short`：17 passed。
- `python -m compileall -q src bench scripts tests`：通过。
- `docker compose config`：通过。
- 临时启动 Streamable HTTP 3099 端口：`/healthz` 返回 `{"status":"ok","transport":"streamable-http"}`。
- 使用 `mcp.client.streamable_http.streamablehttp_client('http://127.0.0.1:3099/mcp')` + `ClientSession.list_tools()`：协议 smoke 通过，临时无 downstream 时 `tools_count=0`。
- `python -m pytest -q --basetemp pytest_tmp_l3_full -p no:cacheprovider -x --tb=short`：全量通过，进度 100%，无失败。
- `python -m bench.cli run --suite bench/cases/csab-gov-mini-seed.yaml --config configs/xa-guard.yaml`：290 条 pass_rate 1.0，`audit_completeness=1.0`，P50 75.14 ms，P95 558.4 ms（P95 未达 PRD 中等档 300 ms）。

未完成 / 客观限制：
- 未执行完整 `docker compose up --build -d` 镜像构建和长期运行验收；本轮只验证了 Compose 配置和本地 HTTP 协议 smoke。
- 未完成生产级国密 SM2/SM3 + TSA、真实 Trae/国产 IDE 弹窗截图、AgentDojo/InjecAgent 外部 benchmark、500+ 国标题库、OPA Rego 合并视图、Linux gVisor/runsc 实测、LangChain SDK 非透传和 CoT faithfulness 实算法。
- AIBOM gateway 已接入 bench supply_chain，但还不是“真实 MCP 插件安装链路”；仅包名+版本的 seed 暂未启用离线漏洞库重判，避免未经审核翻转既有评测基线。

下一步建议：
- 先执行 `docker compose up --build -d xa-guard` 和真实容器内 MCP client smoke，补齐 Compose 一键部署证据。
- 在 Linux 主机验证 `runsc`/gVisor，并把 Gate5 sandbox 从命令构造提升为真实下游 MCP server 沙箱执行证据。
- 做 Trae/Cursor/CodeBuddy/Qoder CN HITL 实测矩阵；不要把 toy probe 写成真实 IDE popup。
- 建 AgentDojo/InjecAgent 最小 adapter 和结果文件，同时扩展 Gate1 对抗集与供应链 case。

## 2026-06-16 +08:00 Codex - 补齐 Gate5 本机沙箱镜像并消除 pytest skip

本次具体做了什么：
- 复查 `docker/sandbox.Dockerfile`、`scripts/build_sandbox_image.sh` 和 `tests/integration/test_sandbox_runner.py`，确认此前 skip 的直接原因是本机缺少 `xa-guard/sandbox:latest` 镜像且 Docker Desktop daemon 未运行。
- 启动 Docker Desktop，等待 `docker info` 成功后，执行 `docker build -f docker/sandbox.Dockerfile -t xa-guard/sandbox:latest .` 构建 Gate5 下游沙箱镜像。
- 使用 `docker image inspect xa-guard/sandbox:latest` 确认镜像存在，用户为 `sandbox`，工作目录为 `/workspace`。
- 运行 `tests/integration/test_sandbox_runner.py`，原本 skip 的沙箱测试已真实执行并通过，验证 Docker 沙箱禁网与只读 rootfs 生效。
- 运行全量 pytest，确认当前不再有 sandbox skip。
- 更新 `status.md`：L2 Competition-trusted 证据闭合；全量测试状态改为 394 passed / 0 skipped；Gate5 沙箱镜像状态改为已构建并实测。

验证：
- `docker build -f docker/sandbox.Dockerfile -t xa-guard/sandbox:latest .`：成功。
- `docker image inspect xa-guard/sandbox:latest --format '{{.Id}} {{.Config.User}} {{.Config.WorkingDir}}'`：成功，输出包含 `sandbox /workspace`。
- `python -m pytest -q --basetemp pytest_tmp_sandbox_recheck -p no:cacheprovider tests\integration\test_sandbox_runner.py -x --tb=short`：1 passed。
- `python -m pytest -q --basetemp pytest_tmp_full_after_sandbox -p no:cacheprovider -x --tb=short`：全量通过，进度 100%，无 skip 行；按上一状态 393 passed / 1 skipped 加本次 sandbox 实测通过，当前为 394 passed / 0 skipped。

未完成 / 下一步：
- 本次只补齐本机 Docker sandbox smoke；没有做 Linux `runsc`/gVisor 实测，也没有做 Docker Compose 一键部署，这两项仍属于 L3。
- 没有重新跑覆盖率、bench 或 Gate1 evaluator；沿用上一轮 L2 复查的覆盖率 82% 与 bench/Gate1 结果。

## 2026-06-16 +08:00 Cursor subagent - L2 完成计划 P0/P1/P2/P4/P5 端到端

本次具体做了什么：
- **P0**：新增 `docs/L2-acceptance-checklist.md`，冻结 Hard L2（PRD：LOC/README/覆盖率/6关测试）与 Competition-trusted L2（bench/Gate1/HITL/沙箱），明确排除 L3 项。
- **P1**：`pyproject.toml` 的 `bench` extra 加入 `pytest-cov`；配置 `[tool.coverage.*]`；全量覆盖率 **82%**（≥50% L2 Hard）；更新 `README.md`（策略目录、命令、audit 口径、L2 文档链接）。
- **P2**：从 PR #2 恢复 `scripts/evaluate_gate1.py` + `tests/test_gate1_evaluator.py`；补回 Gate1 spotlighting metadata、fusion fail-closed、model_detector fail_open 标记及对应单测；Gate1 rule-only 复现：Gate1-scope 60 attack Recall 68.33%、FPR blocking 0、`recall_at_fpr` 输出。
- **P4**：新增 `src/xa_guard/audit/completeness.py`；Gate6/bench 改为实测 `audit_completeness`（非固定 1.0）；bench 290 跑后 `audit_completeness=1.0`（265 条 pipeline 写审计）。沙箱：`scripts/build_sandbox_image.sh` 就绪；**本机 Docker Desktop 未运行**，未能 build `xa-guard/sandbox:latest`，sandbox 集成测试仍 skip。
- **P5**：新增 `docs/L2-verification-commands.md`（pytest/bench/coverage/Gate1/验链/矩阵/fixtures/沙箱一键链）；重写 `status.md` 为 L2 工程完成 + L3 差距分离。

验证：
- `PYTHONPATH=src python -m pytest -q` → 393 passed / 1 skipped
- `pytest --cov=xa_guard --cov=bench` → **82%**
- `python scripts/evaluate_gate1.py --detectors rule` → Gate1-scope recall 0.6833
- `generate_tool_gate_coverage_matrix.py --strict` / `validate_gate3_rule_fixtures.py --strict` → 通过
- `python -m bench.cli run …` → pass_rate 1.0，audit_completeness 1.0

未完成 / 需用户动作：
- 本机启动 Docker Desktop 后执行 `bash scripts/build_sandbox_image.sh` 并重跑 `tests/integration/test_sandbox_runner.py`（期望 0 skip）。
- L3：Trae 实测、AgentDojo、国密、Compose 一键部署、PDF/视频等见 `status.md` L3 段。

## 2026-06-16 20:36 +08:00 Codex - 审核并合并 PR #2 Gate1 真实模型验证

本次具体做了什么：
- 按用户要求审核 GitHub PR `chuali-zi/agent_safety#2`（`codex/gate1-real-model-verification`），重点检查“是否只是空壳、没有接入实际模型”的风险。
- 使用 GitHub connector 拉取 PR 元数据、diff 和评论；PR 无评论线程，GitHub 显示 `MERGEABLE/CLEAN`，无 CI 状态上报。
- 在独立 worktree `D:\race\jiebang-pr2-review` 拉取 PR 分支，避免覆盖主工作区已有 `status.md` 未提交改动。
- 检查核心实现：新增 `scripts/evaluate_gate1.py`，Gate1 fusion 对显式 `fail_open=false` 的不可用模型 detector 改为真实 fail-closed DENY，Gate1 metadata 增加 spotlighting 可审计字段。
- 重点核实真实模型问题：PR 不是把 Qwen3Guard 当成空壳宣传；文档和 evaluator 记录 Qwen3Guard-Gen-0.6B 真实加载、真实进入 Gate1，同时明确 model-only 对 MCP/tool-call 风格输入效果很弱，不能替代规则层。
- 本地验证通过：`PYTHONPATH=src python -m pytest tests\unit\test_gate1_detectors.py tests\test_gate1_evaluator.py -q` 44 passed；`python -m compileall src bench scripts tests` 通过；`git diff --check origin/main..HEAD` 无输出；全量 `PYTHONPATH=src python -m pytest -q` 389 passed / 3 skipped（Docker sandbox 镜像 1 条、OPA binary 2 条）。
- 额外运行新增 Gate1 evaluator rule-only 口径，Gate1-scope 结果与 PR 文档一致：60 个 Gate1-scope attack，Recall 68.33%，ASR 31.67%，FPR blocking 0。
- 已通过 GitHub merge 合并 PR #2，merge commit 为 `262ff24a5c3a488ff1e368cb5ff64d6b14fe262e`。

完成情况：
- PR 审核完成，未发现阻断合并的问题。
- PR 已合入远端 `main`。
- 本地 `origin/main` 已 fetch 到合并后的远端状态；当前主工作区仍保留合并前已有的 `status.md` 未提交改动，未强行覆盖。

未完成 / 风险：
- 本次没有重新跑真实 Qwen CUDA 推理；评审依据是 PR 记录、代码路径、Gate1 evaluator 和本地规则口径回归。
- GitHub PR 没有 CI status check，上述结论依赖本地 worktree 验证。
- Qwen3Guard-Gen-0.6B 虽真实接入，但当前证据显示它不能作为 MCP/tool-call、间接注入、RAG/tool-output poisoning 的主检测器；仍需专门 A/B 集、Recall@FPR、AgentDojo/InjecAgent 和自适应攻击评测。

## 2026-06-05 +08:00 Claude 主 agent（+4 sonnet 子 agent）- AIBOM 生产化（方向 3）

把 `src/xa_guard/aibom/` 从 demo 骨架推进到生产化，落地 status.md 下一步清单第 8 条的 5 项能力。
派出 4 个 sonnet 子 agent 并行各建一个自包含模块（互不改共享文件），主 agent 自建漂移监测 + 总装 + 集成。

本次具体做了什么：
- **CycloneDX schema 校验**（子 agent A）：`schema_validator.py` + 手写 `schema/cyclonedx-1.6.subset.schema.json`；
  jsonschema 优先、缺库走内建结构校验；额外做 bom-ref 引用完整性 / hash 内容 / vuln severity 校验。40 测试。
- **签名/公钥校验**（子 agent B）：`signing.py`，JSF 风格 canonical-JSON 签名；Ed25519（cryptography，真实非对称）、
  SM2（gmssl 缺失→HMAC 降级）、HMAC；trust store `<keyId>.pub`；篡改/未知 keyId fail-closed。21 测试。
- **远程包离线拉取**（子 agent C）：`offline_fetch.py`，`OfflinePackageStore` 严格离线 fail-closed 缓存解析，
  name/version/url 三类 key、sha256 流式校验、原子 index、路径穿越防护、零网络库。24 测试。
- **外部信誉/漏洞库**（子 agent D）：`intel.py` + `data/vulndb.json`（7 包 10 真实 CVE 种子）+ `data/reputation.json`；
  PEP440 版本区间匹配、affected vs potentially_affected、max_severity。26 测试。
- **持续漂移监测**（主 agent）：`drift_monitor.py`，带持久化快照 + JSONL 漂移账本，严重度分级，复用 compare_drift。6 测试。
- **总装**（主 agent）：`gateway.py::admit()` 串起"离线拉包→扫描→漏洞富化→导出→schema 校验→签名验签→漂移"，
  输出 AdmissionResult(decision)；`cli.py` 提供 `xa-aibom admit/bom/validate/drift`（退出码 allow0/warn1/deny2）。
- 集成共享文件改动：scanner.ScanReport 增 `vulnerabilities` 字段；exporter specVersion 1.5→1.6 + vulnerabilities 段；
  rater 纳入 vuln_*/reputation_*/signature_invalid/schema_invalid；pyproject 增 `aibom` extra + `xa-aibom` script。
- 同步把 test_aibom_schema_validator 里 `spec_version=="1.5"` 滞后常量改为 1.6（随 exporter 生产化升级，非业务 bug，已在 worklog 备查）。

测试/验证：
- 全量 `PYTHONPATH=src python -m pytest`：**391 passed / 1 skipped**（skip 为 docker sandbox 镜像缺失，预期）。
  较上一快照 259 passed 净增约 128 条，无回归；supply_chain bench 4 条断言（SCM-001~004）不变。
- 端到端 CLI smoke：urllib3==1.26.5+requests==2.31.0 命中 4 CVE（1 high/3 medium）、CycloneDX 1.6 schema 合规、
  Ed25519 签名并验签 True、二次漂移 D→F 判 high、终判 deny / 退出码 2。

未完成 / 下一步：
- bench supply_chain 仍走旧 `rate_install_request` 简化口径未接 gateway——接入会因漏洞库命中翻转 SCM-003（requests==2.31.0）
  等基线，需重新生成 seed fingerprint 与重判预期决策，列为后续单独一轮（避免本轮静默改评测基线）。
- 真实 MCP 安装链路（gate 级）尚未把 install_plugin 路由到 gateway；漏洞库/信誉库为离线种子快照，非实时 feed；
  SM2 仍是 gmssl 缺失下的 HMAC 降级。

## 2026-06-05 +08:00 Codex 主 agent - 调整 Gate2/3/4 审核指南为策略合规审核导向

按用户反馈“不是主要审核代码，主要审核策略是否合规”，修改 `docs/Gate2-3-4策略审核指南.md`。

本次具体做了什么：
- 将文档标题改为 `Gate2/3/4 策略合规审核指南`，开头明确“主要审核策略是否合规、依据是否充分、证据是否完整；代码只作为辅助验证”。
- 重写审核重点：从“代码/测试/覆盖矩阵能不能跑”调整为“法规/标准/项目依据、risk_level 分级解释、工具能力边界、Gate3 正反例和 bench 证据、是否夸大宣传”。
- 调整审核范围：Gate2 审核风险分级策略，Gate3 审核法规/企业规则策略，Gate4 审核工具能力和数据密级策略；代码文件降级为辅助理解运行语义。
- 调整 Gate2/Gate3/Gate4 各节：要求审核人说明风险等级依据、规则 `source`、合规解释、工具能力是否漏标、机密数据是否可能外流。
- 调整审核结果模板：新增“合规审核结论”，要求分别写 Gate2 风险分级、Gate3 规则来源、Gate4 能力边界、bench 证据是否足够。
- 更新 `docs/README.md` 中该文档的说明，从“策略总账/测试结果”改为“策略合规性、依据和证据”。
- 删除文档中旧的 `policy_count == 30` 测试红点说明，改为当前真实口径：Gate3 31 条 baseline 规则已有正/反例 fixtures 强约束，仍需关注 23 个 trigger 未进入 bench case 的合规证据缺口。
- 同步修正 `status.md` 里 Gate3 状态的一句过时描述，避免继续显示“单测仍有 30 条断言滞后”。

已完成：
- 审核文档现在以策略合规性为主，代码和测试只作为辅助验证步骤。

未完成 / 客观限制：
- 没有修改业务策略、测试代码或运行时逻辑。
- 没有重跑 pytest；本轮是文档口径修改。

## 2026-06-05 +08:00 Codex 主 agent - Spotlighting 默认开启、Gate3 强约束、覆盖矩阵 overlay 总账

按用户明确决策执行三项修改：Spotlighting 默认开启；Gate3 每条规则的正/反例升级为硬约束；覆盖矩阵纳入 baseline+overlay 合并视图，并将 `install_plugin` 纳入统一工具总账。本轮派出 3 个 gpt-5.5 medium 子 agent 做只读调查，分别覆盖 Spotlighting 配置、Gate3 fixtures/schema/validator 落点、覆盖矩阵/工具总账实现；子 agent 均未改文件。

本次具体做了什么：
- 修改 `configs/xa-guard.yaml`：`gate1.spotlighting.enabled` 从 `false` 改为 `true`，默认对非 user 来源加 `<untrusted_source>` 标记。
- 新增 `bench/cases/gate3-rule-fixtures.yaml`：为当前 31 条 Gate3 baseline 规则各提供 1 个正例和 1 个反例。
- 新增 `bench/schema/gate3-rule-fixtures.schema.json` 和 `scripts/validate_gate3_rule_fixtures.py`：validator 会真实执行 Gate3，要求正例命中目标 rule_id、反例不命中目标 rule_id，并校验可选 `expected_decision`。
- 新增 `tests/test_gate3_rule_fixtures_assets.py`：守护 fixture 覆盖所有 baseline rule_id，并运行 validator 的 `--strict`。
- 修改 `policies/baseline/gate3_rules.yaml`：新增 `AIBOM-INSTALL-PLUGIN-SUPPLY-CHAIN`，把 `install_plugin` 纳入 Gate3 trigger。
- 修改 `policies/baseline/gate4_capabilities.yaml`：新增 `install_plugin` capability，能力包含 `NETWORK_EXTERNAL`、`DATA_INGEST`、`FS_WRITE`、`EXEC`，risk_level 为 `red`。
- 修改 deprecated 兼容文件 `policies/baseline/gate2_tool_risks.yaml`：同步补 `install_plugin: red`，实际 layered 运行时仍由 Gate4 capabilities 派生 Gate2 risk。
- 修改 `scripts/generate_tool_gate_coverage_matrix.py`：默认改为读取 `LayeredPolicySource` 的 baseline+accepted overlay 合并视图；显式传 `--gate2/--gate3/--gate4` 时仍保留 legacy 单文件模式。
- 修改 `tests/test_tool_gate_coverage_matrix.py`：断言覆盖矩阵默认纳入 overlay 合并视图，且 `install_plugin` 不再是 bench-only。
- 修改 `tests/unit/test_config.py` 和 `tests/unit/test_gate3.py`：补默认配置断言，并把 Gate3 policy_count 更新为当前 31 条规则。
- 修改 `status.md`：删除“Spotlighting 默认未开”“Gate3 31 vs 30 测试仍失败”“规则正反例未强约束”等过时状态，改为当前仓库状态。
- 修改 `README.md`：同步 Gate1/Spotlighting 当前口径。

验证结果：
- `python -m pytest -q --basetemp pytest_tmp_targeted -p no:cacheprovider tests\unit\test_config.py tests\test_tool_gate_coverage_matrix.py tests\test_gate3_rule_fixtures_assets.py tests\unit\test_gate3.py -x --tb=short`：通过，54 个测试点。
- `python scripts\generate_tool_gate_coverage_matrix.py --strict --json`：通过，policy_view=`layered-merged`，tools=48，gate2=48，gate3_triggers=44，gate4=48，bench_only=0，missing_gate2=0，missing_gate4=0，risk_mismatches=0。
- `python scripts\validate_gate3_rule_fixtures.py --strict --json`：通过，rules=31，fixtures=31，positive=31，negative=31，errors=0，warnings=0。
- `python -m pytest -q --basetemp pytest_tmp_broad -p no:cacheprovider tests\unit\test_gate1.py tests\unit\test_gate1_detectors.py tests\unit\test_gate2.py tests\unit\test_gate3.py tests\unit\test_gate4.py tests\unit\test_layered_policy.py tests\test_tool_gate_coverage_matrix.py tests\test_gate3_rule_fixtures_assets.py tests\test_aibom_bench_supply_chain.py tests\integration\test_bench_smoke.py -x --tb=short`：通过，183 个测试点。
- `python -m pytest -q --basetemp pytest_tmp_full_current -p no:cacheprovider -x --tb=short`：通过；`tests/integration/test_sandbox_runner.py` 因本机缺少 `xa-guard/sandbox:latest` 镜像按预期 skip 1 条。

已完成：
- Spotlighting 默认策略已定为默认开启，并有配置测试守护。
- Gate3 正/反例不再只是文档约定，已变为 fixture/schema/validator/test 的硬约束。
- 覆盖矩阵默认统计 overlay 合并后的有效策略视图。
- `install_plugin` 已进入 Gate3/Gate4/Gate2 layered 派生总账，覆盖矩阵中不再是 bench-only。

未完成 / 客观限制：
- 尚未跑全量 bench、真实模型推理或真实客户端 HITL 弹窗测试。
- Spotlighting 只完成默认开启和定向回归，尚未给出开启/关闭 ASR、Recall/FPR 或 AgentDojo/InjecAgent 对照指标。
- `install_plugin` 的 supply-chain bench 仍主要走独立 AIBOM rater，尚未扩展到完整远程信誉库、签名验证、漏洞库和 provenance/审计闭环。
- Gate3 layered/hot-reload 合并视图仍走 Python predicate，尚未统一接入 Rego engine。

下一步建议：
- 设计 Spotlighting 开关对照评测集，给出默认开启后的可量化收益和误报代价。
- 继续补真实客户端 HITL、gVisor/runsc、AIBOM 生产化和 layered Rego。

## 2026-06-05 +08:00 Codex 主 agent - 新增 Gate2/3/4 策略审核指南

按用户要求，在 docs 下新增给组员使用的审核文档，要求写得傻瓜、清楚，说明怎么审核、审核什么、文件在哪、为什么审核、参考是什么、完成目标是什么。

本次具体做了什么：
- 新增 `docs/Gate2-3-4策略审核指南.md`，按“先记住结论 → 为什么审核 → 审核范围 → 先看哪些文件 → Gate2/Gate3/Gate4 分别怎么审 → 覆盖矩阵怎么用 → 测试怎么跑 → 审核结果模板 → 完成目标 → 红线 → 参考文档”的顺序写。
- 文档里明确当前事实口径：Gate3 31 条规则 / 44 trigger，Gate2/Gate4 48 工具，bench-only 0，仍有 23 个 Gate3 trigger 无 bench case。
- 文档里明确当前已知测试红点：`tests/unit/test_gate3.py::test_clean_call_allows` 仍断言 `policy_count == 30`，但实际已有 31 条规则；要求组员不要私自改测试，应先写入审核结论等负责人确认。
- 更新 `docs/README.md`，把新文档加入目录树、用途表和顶层文档说明。

已完成：
- 组员现在可以按 `docs/Gate2-3-4策略审核指南.md` 逐项审核 Gate2/3/4 策略、覆盖矩阵、正反例和测试结果。
- docs 目录索引已能指向该文档。

未完成 / 客观限制：
- 本轮没有修改业务策略和测试代码。
- 本轮没有重跑 pytest；这是文档新增，不改变运行时能力。

## 2026-06-05 +08:00 Codex 主 agent - Gate2/3/4 策略核查与分工建议准备

按用户要求，客观核查当前 Gate2 / Gate3 / Gate4 策略是否需要继续增添，以便后续给组员分配任务和准备工作文档。本轮没有修改业务策略，也没有修改测试代码。

本次具体做了什么：
- 读取 `status.md`、`docs/PRD.md`、`docs/项目总览.md`、`docs/规则测试样例约定.md`，对照赛题 4 个方向、PRD L3 目标和当前仓库状态。
- 检查 `policies/baseline/gate2_tool_risks.yaml`、`gate3_rules.yaml`、`gate4_capabilities.yaml`、`bench/.log/tool_gate_coverage.md`，确认当前策略事实源、工具总账和覆盖矩阵。
- 检查 `src/xa_guard/gates/gate2_plan.py`、`gate3_policy.py`、`gate4_taint.py` 与 `tests/unit/test_gate3.py`，确认 Gate2 未登记默认 yellow、Gate4 未登记 fail-closed、Gate3 predicate 聚合与测试覆盖现状。
- 运行 `python scripts/generate_tool_gate_coverage_matrix.py --strict`，通过；当前 layered-merged 视图为 tools=48 / gate2=48 / gate3_triggers=44 / gate4=48 / bench_only=0 / gate3_no_bench=23。
- 运行 `python -m pytest -q --basetemp pytest_tmp_gate234_review -p no:cacheprovider tests\unit\test_gate2.py tests\unit\test_gate3.py tests\unit\test_gate4.py tests\test_tool_gate_coverage_matrix.py -x --tb=short`，失败 1 条：`tests/unit/test_gate3.py::test_clean_call_allows` 仍断言 `policy_count == 30`，但当前 Gate3 规则已是 31 条。
- 更新 `status.md`：把策略规模修正为 Gate3 31 条 / 44 trigger、Gate2/Gate4 48 工具、`bench_only=0`，删除 `install_plugin` 仍未登记的过时描述，并记录当前 Gate3 测试断言滞后。

已完成：
- 确认当前 Gate2/3/4 广度基本足够，短期不建议继续盲目横向加策略。
- 确认当前优先任务应转向测试口径修正、Gate3 正反例强约束、23 个无 bench case trigger 的证据补齐、真实客户端 HITL 和评测可信度。

未完成 / 客观限制：
- 没有修改 `tests/unit/test_gate3.py`，因为用户明确要求不能通过改测试来通过测试；该处是否属于陈旧断言需要人工审核后再改。
- 没有运行全量 pytest；本次只跑 Gate2/3/4 相关子集和覆盖矩阵。
- 工作区已有多处未提交改动，本轮未回退、未整理这些非本次产生的改动。

下一步建议：
- 先由负责人确认 `policy_count == 30` 是否可按实际 31 条规则修正；确认后再改测试并重跑 Gate2/3/4 子集。
- 给组员的任务不要写成“继续补规则”，而应写成“补证据、补强约束、补真实演示与评测可信度”。

## 2026-06-05 +08:00 Claude 主 agent - 修 fail-closed 回归：baseline 登记 demo fixture echo

承接上一条：上一轮 status 标出的 2 个集成测试回归（`test_proxy_smoke` / `test_mcp_e2e`），按用户指示用"路线 1"修复——在 baseline 给 demo fixture 工具登记 Gate2/Gate4 capability，保持 fail-closed 不破窗。

本次具体做了什么：
- 定位 fixture 工具集：`tests/integration/_fixture_echo_server.py` 与 `_fixture_e2e_server.py` 用 `echo` / `exec_command` / `grant_permission`；其中 `exec_command`(red) / `grant_permission`(red) 已登记，仅 `echo` 缺登记，命中 Gate4 `_default_cap`（output=CONFIDENTIAL+NETWORK_EXTERNAL）→ OUTBOUND 必然 DENY。
- `policies/baseline/gate4_capabilities.yaml`：新增 `echo`，`capabilities: []`、`input_max_taint: CONFIDENTIAL`、`output_taint: PUBLIC`、`risk_level: green`（无外网/通知能力，OUTBOUND 不再 DENY）。
- `policies/baseline/gate2_tool_risks.yaml`：新增 `echo: green`，与 Gate4 登记保持一致（覆盖默认配置走的 legacy Gate2 路径）。
- 同步更新 `status.md`：把"⚠️ 已知 broken"段改写为"测试状态：259 passed/1 skip 全绿 + 已修复说明"；baseline 规模 46→47 工具、矩阵 total 47→48；删掉下一步第 1 优先级"先修回归"并重排编号；订正 L2 段与 bench 表注释。

验证结果：
- `pytest tests/integration/test_proxy_smoke.py tests/integration/test_mcp_e2e.py tests/test_tool_gate_coverage_matrix.py`：6 passed。
- 全量 `PYTHONPATH=src python -m pytest`：**259 passed / 1 skipped / 0 failed**（1 skip 为 sandbox 镜像未构建，预期）。
- `python scripts/generate_tool_gate_coverage_matrix.py --strict`：通过，tools=48 / gate2=47 / gate4=47 / missing_gate2=0 / missing_gate4=0 / risk_mismatches=0。

已完成：
- 2 个 fail-closed 回归测试转绿；fail-closed 兜底语义保持不变（未登记工具仍一律从严），只是把 demo fixture 显式登记为良性绿工具。
- Gate2/Gate4 对 echo 的登记一致，覆盖矩阵 strict 无漂移。

未完成 / 客观限制：
- 仅登记了 `echo` 一个 demo fixture；若后续新增 demo 工具仍需在 baseline 显式登记，否则会被 fail-closed 拒。
- 没有重跑 bench / verify_audit（本次改动不影响 bench 已登记工具与审计链）。

## 2026-06-05 +08:00 Claude 主 agent - 按 AGENTS.md 重写 status.md 为当前仓库状态

按用户要求"按照 AGENTS.md 的要求更新 status"。AGENTS.md 明确 status.md 应描述**当前仓库状态**（差什么/要改什么/距 PRD 多远），不是顶层追加的日志，过时状态/日志不应留在 status.md。本轮没有读取或维护 implementation-notes.html（git 已删除）。

本次具体做了什么：
- 只读核对 Codex 主 agent 上一轮策略重构的真实落地：`policies/` 分层重构到 `policies/baseline/`（git mv 保留历史，旧平铺路径废弃）；risk_level 单一事实源收敛到 `gate4_capabilities.yaml`（`layered.py` 新增 `_derive_tool_risks_from_caps()`，manifest 移除 tool_risks 条目）；Gate2 fail-open 默认 GREEN→YELLOW；Gate4 `_default_cap` 改 fail-closed（input_max=PUBLIC / output=CONFIDENTIAL / NETWORK_EXTERNAL）；Gate4 OUTBOUND 死代码已清为单一 DENY 路径；新增 `docs/risk_classification_basis.md`。
- 跑全量 `pytest`：**257 passed / 2 failed / 1 skipped**。定位 2 个失败为真实回归：`test_proxy_smoke` 与 `test_mcp_e2e` 用未登记的 `echo` fixture，fail-closed `_default_cap`（output=CONFIDENTIAL + NETWORK_EXTERNAL）导致任何未登记工具在 Gate4 OUTBOUND 必然 DENY，`benign_allowed` 由 True 变 False。已用脚本逐 gate 追踪确认（gate4_taint OUTBOUND DENY）。1 skip 为 sandbox 镜像未构建，预期。
- 核对当前 baseline 规模与覆盖矩阵：Gate3 30 规则/43 trigger、Gate4 46 工具、Gate2 派生 46、敏感 29；矩阵 missing_gate2/4=0、risk_mismatches=0、bench_only=1、gate3_no_bench=23。bench last_report 290 条 pass_rate 100%。
- **重写 status.md**：删掉全部带时间戳的"最新状态快照"日志段与旧平铺路径，改为当前状态文档：一句话定位、已知 broken（2 集成测试回归 + 根因 + 两条修复路线）、本轮已还工程债表（一档①②③/二档④⑤）、分层策略目录结构、逐关卡状态、4 方向贴合度、空壳清单、bench 指标、距 PRD 差距、下一步优先级。

已完成：
- status.md 已符合 AGENTS.md"描述当前状态、不留过时日志"的要求，路径与规模与当前代码一致。
- 把 fail-closed 硬化引入的 2 个集成测试回归如实写进 status，未掩盖。

未完成 / 客观限制：
- 没有修复这 2 个回归测试（用户只要求更新 status；修复涉及"给 fixture 登记 capability vs 测试注入 capability"的产品决策，已列为 status 下一步第 1 优先级）。
- 没有重跑 bench / verify_audit（沿用现有 last_report 与既有验链结论）；本机仍无模型依赖，未复现真实 Qwen。

下一步建议：
- 先修 fail-closed 回归（给 demo fixture 登记 baseline capability，或集成测试注入测试用 capability 表），让 E2E 重新证明 fail-closed 正确性。

## 2026-06-04 23:20:17 +08:00 Codex 主 agent - 补规则样例约定与工具覆盖矩阵

按用户要求处理 `status.md` 顶部二档事项：“规则无逐条正/反例绑定”和“没有覆盖率矩阵”。本轮使用 3 个子 agent 做只读协助调查：分别检查 Gate3 规则正/反例现状、覆盖率矩阵口径、文档落点。未读取或维护 `implementation-notes.html`。

本次具体做了什么：
- 新增 `docs/规则测试样例约定.md`：明确 Gate3 扩规则前应有“一规则一对正/反例”，规定正例/反例命名、bench case 字段、`policy_refs`、`expected_decision`、`case_kind` 和验收命令。
- 在同一文档中补充阳历/公历测试样例约定：日期使用 ISO 8601，默认北京时间 `Asia/Shanghai`，不把“今天/明天/春节前/农历正月”等相对或农历表达作为 oracle；需要相对时间时显式写 `reference_date`。
- 新增 `scripts/generate_tool_gate_coverage_matrix.py`：读取 Gate2/Gate3/Gate4/bench 四源，生成“工具 × Gate 覆盖矩阵”到 `bench/.log/tool_gate_coverage.md`；`--strict` 阻断 Gate3 trigger 缺 Gate2/Gate4、Gate2/Gate4 risk 漂移、非法 risk/taint。
- 新增 `tests/test_tool_gate_coverage_matrix.py`：守护当前 baseline 中 Gate3 trigger 对 Gate2/Gate4 无缺口、同名 risk 无漂移，并确认当前已知 bench-only 缺口 `install_plugin` 被显式报告。
- 更新 `docs/XA-Bench-对抗测试规则.md`：补规则样例、阳历日期、覆盖率矩阵状态码和校验命令。
- 更新 `docs/HACK-BENCH-组员提交规范.md`：补提交侧日期可复现要求和规则正/反例要求。
- 更新 `docs/README.md`：把 `docs/规则测试样例约定.md` 纳入文档目录。
- 更新 `status.md`：记录二档脚手架当前状态、矩阵结果和仍未完成的强校验缺口。

验证结果：
- `python scripts\generate_tool_gate_coverage_matrix.py --strict`：通过，生成 `bench\.log\tool_gate_coverage.md`；结果为 `tools=47`、`gate2=46`、`gate3_triggers=43`、`gate4=46`、`bench=24`、`missing_gate2=0`、`missing_gate4=0`、`risk_mismatches=0`、`bench_only=1`、`gate3_no_bench=23`。
- `python scripts\validate_csab_gov_mini.py --strict`：通过，290 条 case errors=0/warnings=0，并刷新 `bench\.log\coverage.md`。
- `python -m pytest -q --basetemp pytest_tmp_rule_matrix -p no:cacheprovider tests\test_tool_gate_coverage_matrix.py tests\test_csab_gov_mini_assets.py`：通过，10 个测试点。
- `python -m pytest -q --basetemp pytest_tmp_gate3_rules -p no:cacheprovider tests\unit\test_gate3.py -x --tb=short`：通过，46 个 Gate3 测试点。

已完成：
- 二档里的“覆盖率矩阵”已有可运行脚本、报告和测试守护，不再只能肉眼比对三份 YAML。
- “一规则一对测试样例”与阳历日期口径已形成文档约定，并同步到 bench 维护文档和 hack 提交规范。

未完成 / 客观限制：
- 还没有把“一规则一对正/反例”升级为独立 fixture/schema/validator 的强制校验；当前仍主要依赖文档约定和现有 Gate3 单测。
- 覆盖矩阵发现 `install_plugin` 仍是 bench-only 工具，当前 supply-chain bench 仍走 AIBOM 简化路径，未登记进 Gate2/Gate3/Gate4。
- 覆盖矩阵发现 23 个 Gate3 trigger 当前无 bench case 覆盖；本轮没有补这些 case。
- 覆盖矩阵目前只覆盖 baseline + bench，没有覆盖真实租户 overlay 合并视图。

下一步建议：
- 新增 `bench/cases/gate3-rule-fixtures.yaml`、schema 和 validator，把每条 Gate3 规则的正/反例变成硬约束。
- 决定 `install_plugin` 是否纳入统一工具总账；若纳入，应补 Gate2/Gate4 capability 和对应策略/测试。
- 为 23 个 `NO_BENCH_CASE` trigger 分批补 bench case，或建立显式豁免清单。

## 2026-06-04 22:23:39 +08:00 Codex 主 agent - 安装本地 OPA 并补真实 CLI 测试

按用户要求安装 / 下载 OPA，并补齐 OPA/Rego 后端测试。本轮没有读取或维护 `implementation-notes.html`。

本次具体做了什么：
- 上网确认 OPA 官方 Windows amd64 latest 下载入口为 `https://openpolicyagent.org/downloads/latest/opa_windows_amd64.exe`。
- 新增真实 OPA smoke 测试到 `tests/unit/test_gate3.py`：一条显式传 `opa_path=tools/opa/opa.exe`，一条验证默认发现仓库本地 OPA；两条都使用 `strict_opa=true`，确保执行真实 `opa eval`。
- 运行新增默认发现测试，确认当前代码缺少本地 `tools/opa/opa.exe` 发现逻辑，测试按预期失败。
- 下载 OPA 到 `tools/opa/opa.exe`。版本输出为 OPA 1.17.0 / Rego v1 / windows/amd64；本地 SHA256 为 `D319E1ABCA6B1683E79E4E3DDB840B098C45A9257426BA998917DAC8D83B7574`。
- 修改 `.gitignore`，忽略 `tools/opa/opa.exe`，避免把约 97MB 的本地工具二进制作为源码提交。
- 修改 `src/xa_guard/policy/rego.py`：`RegoPolicyEngine` 的 OPA 查找顺序变为显式 `opa_path` → PATH 中的 `opa` → 仓库本地 `tools/opa/opa.exe`。
- 真实 OPA smoke 首次失败后，按调试流程打印生成的 Rego 和 OPA stderr，定位到 OPA 1.17.0 在本机对 Python 临时目录 Windows 绝对路径处理失败。随后把 `_evaluate_opa()` 改为 `cwd=tmpdir` 并使用相对路径 `gate3.rego` / `input.json`，真实 smoke 通过。
- 更新 `status.md` 顶部快照，记录本地 OPA 版本、hash、测试结果和剩余限制。

验证结果：
- `tools\opa\opa.exe version`：OPA 1.17.0，Rego Version v1，Platform windows/amd64。
- `Get-FileHash -Algorithm SHA256 tools\opa\opa.exe`：`D319E1ABCA6B1683E79E4E3DDB840B098C45A9257426BA998917DAC8D83B7574`。
- `python -m pytest -q --basetemp pytest_tmp_opa_real -p no:cacheprovider tests\unit\test_gate3.py::test_rego_backend_evaluates_with_real_local_opa tests\unit\test_gate3.py::test_rego_backend_discovers_local_opa_by_default -x --tb=short`：通过。
- `python -m pytest -q --basetemp pytest_tmp_opa_gate3 -p no:cacheprovider tests\unit\test_gate3.py -x --tb=short`：通过，46 个 Gate3 测试点。
- `python -m pytest -q --basetemp pytest_tmp_opa_related -p no:cacheprovider tests\unit\test_gate2.py tests\unit\test_gate3.py tests\unit\test_gate4.py tests\unit\test_layered_policy.py -x --tb=short`：通过。
- `python -m pytest -q --basetemp pytest_tmp_opa_full -p no:cacheprovider -x --tb=short`：通过；`tests\integration\test_sandbox_runner.py` 因当前 shell 未发现 Docker 被 skip。

已完成：
- 本机仓库内已有可执行 OPA：`tools/opa/opa.exe`。
- Gate3 Rego 后端已真实跑过 `opa eval`，不再只是 fallback。
- 测试已覆盖显式 OPA 路径和默认本地发现。
- Windows 路径调用 OPA 的问题已修复。

未完成 / 客观限制：
- `tools/opa/opa.exe` 被 `.gitignore` 忽略，不会随源码提交；新环境需要重新下载或把 OPA 安装到 PATH。
- 真实 OPA smoke 覆盖的是 Gate3 legacy `policy_file` 路径；`LayeredPolicySource` 的 baseline+overlay 热加载合并视图仍未统一接入 Rego engine。
- 尚未提供 OPA bundle 导出、版本锁定下载脚本、OPA 评估失败时的 fail-closed 配置策略。

下一步建议：
- 加一个轻量下载脚本或 CI cache 步骤，让新环境能自动准备 `tools/opa/opa.exe`。
- 把 `LayeredPolicySource` 合并后的规则集接到 `RegoPolicyEngine`。
- 设计 OPA 不可用 / eval 失败时的生产策略：fail-closed、降级 fallback，或触发人工审批，并写入审计。

## 2026-06-04 22:09:48 +08:00 Codex 主 agent - Gate3 OPA/Rego 后端 MVP

按用户要求继续完善 OPA/Rego 后端。本轮没有读取或维护 `implementation-notes.html`，只修改 Gate3/Rego 相关代码、测试，以及根目录 `status.md` 和本工作日志。

本次具体做了什么：
- 读取 `status.md`、`AGENTS.md`、`src/xa_guard/gates/gate3_policy.py`、`src/xa_guard/policy/compiler.py`、`tests/unit/test_gate3.py`、`src/xa_guard/config.py`、`policies/enterprise-l3.yaml` 等文件，确认当前明确缺口是 `backend=rego` 仍为 `NotImplementedError`。
- 新增 `src/xa_guard/policy/rego.py`：实现 PolicyRule predicate DSL 到 Rego module 的 AST 转译，覆盖当前 30 条 baseline predicate 的主要形态，包括 `and/or/not`、比较、`in/not in`、`contains()`、`args.get()`、`args[...]`。
- 新增 `RegoPolicyEngine`：若找到或配置 `opa_path`，通过 `opa eval --data gate3.rego --input input.json data.xa_guard.gate3.hit` 评估命中规则；若没有 OPA binary 且未开启严格模式，则使用与现有 Python predicate 相同语义的 fallback。
- 修改 `src/xa_guard/gates/gate3_policy.py`：`backend=rego` 不再抛 `NotImplementedError`，而是实例化 `RegoPolicyEngine`；`strict_opa=true` 且无 OPA binary 时 fail-fast；Gate3 结果 metadata 增加 `rego_mode` 和 `opa_available`。
- 修改 `tests/unit/test_gate3.py`：把原先“Rego 后端应抛错”的测试改为验证 Rego backend fallback 可命中、严格模式缺 OPA 会抛错、当前 DSL 能生成 Rego module。
- 运行测试并更新 `status.md` 顶部状态快照，客观标注“真实 OPA CLI 路径本轮未实测”。

验证结果：
- `python -m pytest -q --basetemp pytest_tmp_rego -p no:cacheprovider tests\unit\test_gate3.py -x --tb=short`：通过。
- `python -m pytest -q --basetemp pytest_tmp_rego_related -p no:cacheprovider tests\unit\test_gate2.py tests\unit\test_gate3.py tests\unit\test_gate4.py tests\unit\test_layered_policy.py -x --tb=short`：通过。
- `python -m pytest -q --basetemp pytest_tmp_rego_full -p no:cacheprovider -x --tb=short`：通过；`tests\integration\test_sandbox_runner.py` 因当前 shell 未发现 Docker 被 skip。

已完成：
- Gate3 的 `backend=rego` 已从空壳变成可实例化、可评估、可配置 OPA CLI 的 MVP。
- 当前 30 条 baseline predicate 已有转译覆盖测试，Gate3 相关回归和全量 pytest 均通过。
- 生产配置可用 `strict_opa=true` 避免无 OPA 环境误走 fallback。

未完成 / 客观限制：
- 当前环境 `Get-Command opa` 未发现 OPA binary，因此没有执行真实 OPA CLI eval；本轮只验证了 Rego module 生成和本地 fallback 行为。
- `prefer_layered=true` 的 `LayeredPolicySource` 仍返回 Python compiled predicates，尚未把 overlay/hot-reload 的合并视图交给 Rego engine。
- Rego 转译器只覆盖当前 DSL 形态；后续若引入更复杂表达式，需要扩展 AST 白名单和 Rego 生成测试。

下一步建议：
- 在安装 OPA 的环境运行一条真实 `backend=rego, strict_opa=true` smoke，并把生成 module 的语法/语义结果纳入 CI。
- 将 `LayeredPolicySource` 的 merged policy 也接入 `RegoPolicyEngine`，让 baseline+overlay 热加载后可选择统一 Rego 执行。
- 若要把 Rego 作为生产主后端，补 Rego bundle 导出、OPA 版本约束和策略评估失败时的 fail-closed 产品策略。

## 2026-06-04 21:55:12 +08:00 Codex 主 agent - Gate2/Gate3/Gate4 完成度侦察

按用户要求侦察当前仓库里 Gate2、Gate3、Gate4 这一串的整体完成度。本轮没有读取或维护 `implementation-notes.html`，没有修改产品逻辑、策略 YAML 或测试代码；只更新了 `status.md` 和本工作日志。

本次具体做了什么：
- 读取 `status.md` 和 `log.md`，确认此前 Gate2/Gate3/Gate4 的 baseline 错位已经在 2026-06-02 多轮修复中补齐，当前最新主状态又叠加了 Gate5 工作区改动。
- 核对 `src/xa_guard/pipeline.py`，确认当前执行顺序仍是 Gate1 → Gate2 → Gate4(in) → Gate3 → Gate5 → executor → Gate4(out) → Gate6；Gate2/Gate4/Gate3 属于同一轮执行前决策聚合，Gate3 DENY 可覆盖 Gate2 REQUIRE_APPROVAL。
- 核对 `src/xa_guard/gates/gate2_plan.py`：Gate2 负责读取工具风险，green 放行、yellow 告警、red 触发 REQUIRE_APPROVAL/fallback；真正 MCP elicitation 与 approval token 不在 Gate2 内签发。
- 核对 `src/xa_guard/gates/gate3_policy.py`：Gate3 负责加载 Python predicate 策略并聚合 DENY > REQUIRE_APPROVAL > WARN > ALLOW；`backend=rego` 仍保留为 M3 占位，当前未实现。
- 核对 `src/xa_guard/gates/gate4_taint.py`：Gate4 负责入向敏感扫描、工具输入污点上限、出向 confidential 外发阻断；layered 模式可从全局 `LayeredPolicySource` 读取 capability 和敏感模式。
- 用脚本统计当前策略资产：30 条 policy rule、46 个 tool risk、46 个 tool capability、29 条 sensitive pattern、43 个唯一 Gate3 trigger；43 个 trigger 均已登记 Gate2 risk 与 Gate4 capability，同名 risk level 未发现不一致；`policies/overlay/` 只有 `_template`，没有真实租户 overlay。
- 运行 Gate2/Gate3/Gate4 相关定向测试与 bench 元数据检查。

验证结果：
- `python -m pytest -q -p no:cacheprovider --basetemp pytest_tmp_gate234_scout tests\unit\test_gate2.py tests\unit\test_gate3.py tests\unit\test_gate4.py tests\unit\test_layered_policy.py -x --tb=short`：通过；收集口径为 111 个测试点（14 + 42 + 22 + 33）。
- `python scripts\enrich_csab_gov_mini.py --check`：通过，`bench/cases/csab-gov-mini-seed.yaml` 元数据为最新。
- 策略统计脚本输出：rules=30、tool_risks=46、tool_capabilities=46、sensitive_patterns=29、unique_triggers=43、trigger_missing_risk=[]、trigger_missing_capability=[]、risk_cap_level_mismatch=[]、overlay_dirs=['_template']。

当前判断：
- Gate2 约 80%：工具风险分级、yellow/warn、red/HITL 触发、layered 读取和测试覆盖已完成；真实客户端 UI 证据、审批人强身份和更细粒度产品策略仍未完整。
- Gate3 约 70%：30 条政企/国标规则、predicate 编译、决策聚合和 baseline 对齐已完成；OPA/Rego、规则覆盖评测、异常 fail-closed 策略和生产级策略治理仍未完成。
- Gate4 约 75%：三色污点、递归敏感扫描、工具能力边界、外发 confidential 阻断、敏感模式 baseline 已完成；完整 DLP、更多上下文传播、streamable/http 场景和 overlay 一致性强约束仍未完成。
- Gate2/Gate3/Gate4 串联整体约 75%：demo/规则链路已经比较扎实，可以支撑赛题方向 2 的核心演示；距离 L3 政企原型还差真实租户 overlay、统一工具目录、OPA/Rego、真实 MCP/客户端证据和 bench 指标并入。

未做什么 / 客观限制：
- 本轮没有运行全量 pytest、bench 290 全量执行或真实 MCP E2E；只做 Gate2/Gate3/Gate4 定向测试和 bench 元数据检查。
- 本轮没有修改 Gate2/Gate3/Gate4 逻辑，也没有清理当前工作区已有的其他未提交改动。
- 当前完成度估计基于仓库代码、策略资产和定向测试，不等同于真实生产环境压测或真实客户端人工验收。

## 2026-06-04 14:54:42 +08:00 Codex 主 agent - Gate5 Docker/gVisor 真沙箱执行推进

按用户要求，本轮先读 `status.md` 了解仓库状态，再上网参考 OpenAI Codex sandbox 设计，然后推进 Gate5。没有读取或维护 `implementation-notes.html`。

本次具体做了什么：
- 侦察当前仓库：确认 `status.md` 中 Gate5 仍是主要空位，原先 `src/xa_guard/gates/gate5_sandbox.py` 只输出 `native/docker/docker_gvisor` 路由 metadata，`src/xa_guard/proxy/downstream.py` 未消费该 metadata，下游 MCP server 仍直接裸调用。
- 使用 2 个 gpt-5.5 medium 子 agent 做只读并行侦察：一个梳理 Gate5 当前实现和缺口，一个梳理最小 TDD 测试策略。两个子 agent 都未改文件。
- 上网参考 Codex sandbox：确认 Codex 的核心思路是对 spawned commands 施加真实边界，而不是只做审计标记；Linux 侧参考 bubblewrap/Landlock/seccomp 的语义，尤其是默认只读、显式 writable roots、网络按策略隔离、敏感元数据路径重新保护。由于本仓库是 Python/MCP demo，本轮类比落地为 Docker/gVisor 执行 MVP。
- 新增 `src/xa_guard/sandbox.py`：定义 `SandboxPolicy`、从 Gate5 结果抽取策略、构造 `docker run` 命令。命令包含 `--network none`、`--read-only`、`--cap-drop ALL`、`--security-opt no-new-privileges`、`--pids-limit`、`--memory`、`--cpus`、只读挂载 workspace 到 `/workspace`，`docker_gvisor` 模式追加 `--runtime runsc`。
- 修改 `src/xa_guard/gates/gate5_sandbox.py`：Gate5 继续负责按 risk 路由，但现在输出 executor 可消费的结构化字段，包括 `sandbox_enforced`、`network_disabled`、`readonly_rootfs`、资源限制、workspace mount 策略等。
- 修改 `src/xa_guard/proxy/downstream.py`：`DownstreamRouter.call_tool()` 现在会读取 Gate5 sandbox policy；`native` 继续使用常驻下游 session，`docker/docker_gvisor` 则临时通过 Docker stdio MCP server 调用下游，调用后关闭。
- 修改 `src/xa_guard/gates/gate6_audit.py` 和 `src/xa_guard/types.py`：Gate6 审计 JSONL 新增 `gen_ai.tool.sandbox.mode/enforced/image/runtime`，让事后能看到本次工具调用使用的沙箱策略。
- 修改 `src/xa_guard/config.py`：让程序化默认 `XAGuardConfig()` 与 demo YAML 保持一致，Gate5 默认 `enabled=False`，避免无 Docker 环境在普通 E2E 中误触发真实 Docker。
- 修改 `configs/xa-guard.yaml`：补全 Gate5 sandbox 默认配置项，仍保持 demo 默认禁用 Docker。
- 新增/扩展测试：`tests/unit/test_sandbox_policy.py`、`tests/unit/test_downstream_sandbox.py`、`tests/integration/test_sandbox_runner.py`、`tests/unit/test_config.py`，并扩展 `tests/unit/test_gate5.py`、`tests/unit/test_gate6_audit.py`。测试覆盖 Gate5 输出契约、downstream 不绕过 sandbox、Docker 命令安全参数、审计字段、默认配置一致性。真实 Docker smoke 在本机未安装 Docker 时 skip。
- 刷新 `bench/.log/last_results.json`、`bench/.log/last_report.json`、`bench/.log/report.html`。

验证结果：
- `PYTHONPATH=src python -m pytest -q --basetemp pytest_tmp_full_sandbox -p no:cacheprovider`：通过；新增 Docker smoke 1 条因当前机器未安装 Docker 被 skip。
- `python scripts/enrich_csab_gov_mini.py --check`：通过，bench YAML 元数据最新。
- `PYTHONPATH=src python -m bench.cli run --suite bench\cases\csab-gov-mini-seed.yaml --config configs\xa-guard.yaml`：通过，290 条，pass_rate 1.0，ASR 0.0，FPR 0.0，Recall 1.0，P50/P95 54.25/85.59 ms。
- `PYTHONPATH=src python scripts\verify_audit.py --path logs\audit\audit.jsonl`：通过，15526 条记录，0 chain errors，0 missing-field records。

已完成：
- Gate5 从“只输出路由决策”推进到“可执行 Docker/gVisor sandbox 接入点”。
- 下游 MCP stdio 调用已经能按 Gate5 策略选择 native 常驻 session 或 Docker/gVisor 临时 session。
- 审计记录已经能保存实际 sandbox mode/runtime/image/enforced 证据。
- 默认 demo/测试环境不会因为没有 Docker 而误触发真实 Docker；显式开启 Gate5 时才走真实 Docker/gVisor。

未完成 / 客观限制：
- 当前机器没有 Docker，真实 Docker smoke 被 skip；因此本轮没有在本机实际跑通 `xa-guard/sandbox:latest` 镜像。
- 仓库仍未提供 `xa-guard/sandbox:latest` 镜像构建文件或发布流程；下一步应补 Dockerfile/镜像构建脚本，并在有 Docker/gVisor 的 Linux 环境跑真实 smoke。
- 目前 Docker 沙箱只支持 stdio downstream；streamable-http downstream 仍未实现沙箱化。
- 这不是 Codex 那种 OS-native Landlock/seccomp/Seatbelt/Windows restricted-token 级别实现；本轮是适配当前 Python demo 的 Docker/gVisor MVP。

下一步建议：
- 补 `docker/sandbox.Dockerfile` 或等价构建入口，确保镜像内含 Python、项目代码依赖和 MCP runtime。
- 在 Linux + Docker + runsc 环境跑 `tests/integration/test_sandbox_runner.py`，再补 MCP 真实沙箱 E2E。
- 将 Docker 不可用、镜像缺失、runsc 缺失时的产品策略固定为 fail-closed / degrade / require_approval，并进入配置和审计。

## 2026-06-04 +08:00 Codex 主 agent - Gate2/Gate3/Gate4 分层职责只读解释

按用户要求，以老师讲解口吻核对 Gate2、Gate3、Gate4 以及 baseline/overlay 双层策略在当前代码里的实际分工。本轮只读检查了 `status.md`、`configs/xa-guard.yaml`、`src/xa_guard/pipeline.py`、`src/xa_guard/gates/gate2_plan.py`、`src/xa_guard/gates/gate3_policy.py`、`src/xa_guard/gates/gate4_taint.py`、`src/xa_guard/policy/layered.py`、`src/xa_guard/policy/monotonicity.py`、`policies/baseline_manifest.yaml`、`policies/tool_risks.yaml`、`policies/tool_capabilities.yaml`、`policies/enterprise-l3.yaml` 和 `policies/overlay/` 模板。

本次具体做了什么：
- 确认当前 pipeline 顺序是 Gate1 → Gate2 → Gate4(in) → Gate3 → Gate5 → executor → Gate4(out) → Gate6，其中 Gate2/Gate4/Gate3 属于执行前同一轮决策聚合。
- 确认 Gate2 负责工具风险分级和 HITL 审批触发，读取 `tool_risks`；Gate3 负责国标/企业规则 predicate 命中与 DENY/REQUIRE_APPROVAL/WARN 聚合，读取 `policy_rules`；Gate4 负责工具能力、敏感数据污点和出入向信息流拦截，读取 `tool_capabilities` 与 `sensitive_patterns`。
- 确认当前配置 `prefer_layered: true`，Gate2/Gate3/Gate4 优先共享 `LayeredPolicySource` 的 baseline+overlay 合并视图；但 `policies/overlay/` 当前只有 `_template` 和说明文件，没有真实租户 overlay，因此实际主要是 baseline 生效。
- 确认 baseline manifest 当前把国标兜底分成 4 类资源：`enterprise-l3.yaml` 给 Gate3，`tool_risks.yaml` 给 Gate2，`tool_capabilities.yaml` 和 `sensitive_patterns.yaml` 给 Gate4。

未做什么 / 客观限制：
- 本轮没有修改 Gate2/Gate3/Gate4 的产品逻辑、策略 YAML 或测试。
- 本轮没有运行 pytest、bench 或 MCP E2E，因为用户问题是架构解释和现状核对，不是要求验证功能变更。
- `bundle_sha` 现状仍按 baseline + 所有 overlay 文件字节计算，包含之后可能被拒绝的 overlay 文件；这与“仅当前生效策略快照”的语义仍存在已知偏差。
- overlay 新增 Gate3 trigger 时，当前仍主要靠测试约束 baseline 对齐，尚未在 overlay merge 阶段强制要求同时新增 Gate2 risk 与 Gate4 capability。

## 2026-06-02 +08:00 Codex 主 agent — Gate2/3/4 baseline policy 可扩展与严格对齐

按用户要求，本轮目标是先让 policies 具备可扩展 baseline/overlay 口径，再严格审查并补齐 Gate2/Gate3/Gate4 baseline 对齐。期间使用多个子 agent 做只读审查和分项建议：先由 xhigh 审查指出 Gate3 triggers 与 Gate2/Gate4 登记严重错位，再由多个 medium agent 分别建议 Gate2 风险、Gate4 能力、敏感模式扩展，之后由验证 agent 和最终 xhigh agent 多轮核验。本轮没有提交 git commit，也没有读取或维护 implementation HTML。

本次具体做了：
- 扩展 `policies/tool_risks.yaml`：baseline 工具风险从原先少量 demo 工具扩到 46 个工具，覆盖 Gate3 当前 43 个唯一 trigger；训练/微调/部署、审计/权限/备份/加密策略、数据库导出、支付、系统发布、生成内容对外导出等政企高风险动作按 red/yellow 重新归类。
- 扩展 `policies/tool_capabilities.yaml`：baseline 工具能力扩到 46 个工具；补 `DATA_EXPORT`、`DATA_INGEST`、`POLICY_ADMIN`、`AUTHZ_ADMIN`、`AUDIT_ADMIN`、`MODEL_CALL`、`MODEL_TRAINING`、`MODEL_DEPLOY`、`CONTENT_PUBLISH`、`PAYMENT` 等能力口径；`call_model` 明确带 `NETWORK_EXTERNAL`，CONFIDENTIAL 输入不能外发到外部模型边界。
- 扩展 `policies/sensitive_patterns.yaml`：敏感模式扩到 29 条，补身份证号、手机号、银行卡样式、统一社会信用代码、邮箱、内网 IP、Bearer/JWT/API token/private key/AKIA/GitHub PAT、中文密级和内部资料标识。这里仍只是 regex baseline 兜底，不等同完整 DLP。
- 修改 `src/xa_guard/gates/gate4_taint.py`：敏感扫描现在递归扫描 dict key 和 value，修复 `{"password": "hunter2"}` 这类 key 敏感但 value 不明显的问题；同时为 routing 字段做更细的误伤控制，普通 `to=ops@example.com` 不再被当正文泄密，但 `to=AKIA...@example.com`、`recipient=身份证...`、`channel=secret_key=...` 仍会升级 CONFIDENTIAL 并 DENY。
- 修改 `policies/enterprise-l3.yaml`：`GBT-22239-8.1.4.2` 从跨域留痕 warn 收紧为跨域审批 require_approval，并把 `cross_domain_call` 纳入 predicate；内部信息通过 `send_email/post_url/send_notification/cross_domain_call` 跨域外发至少需要审批。
- 修改 `bench/cases/csab-gov-mini-seed.yaml`：同步 9 个内部 `post_url` 跨域 case（DATA-016..021、INTP-003/008/013）预期从 `warn` 升为 `require_approval`，并运行 `scripts/enrich_csab_gov_mini.py` 重算 fingerprint，保持 bench YAML 幂等。
- 新增/扩展测试：`tests/unit/test_layered_policy.py` 增加 Gate3 triggers 必须有 Gate2/Gate4 profile、Gate2/Gate4 risk level 一致、外部工具拒绝 CONFIDENTIAL、模型调用外部边界、结构化敏感样本覆盖等断言；`tests/unit/test_gate4.py` 增加 key 敏感扫描、layered 普通邮件目的地不误伤、正文邮箱仍命中、routing 字段高置信秘密仍命中；`tests/unit/test_gate3.py` 增加 `cross_domain_call` 内部跨域审批断言。

审查与修复过程：
- 初始 xhigh 审查指出 P0：Gate3 43 个 trigger 中有大量工具缺 Gate2/Gate4 baseline 登记，未知工具会偏 fail-open。
- 分项扩展后，验证 agent 确认 43/43 triggers 均有 Gate2 risk 和 Gate4 capability，且同名 risk level 一致。
- 第一轮最终 xhigh 发现两个 P1：`call_model` 没有 `NETWORK_EXTERNAL`、内部 `send_email/send_notification` 只 warn。本轮已分别修为 `call_model` 外部边界、内部跨域 require_approval。
- 第二轮 xhigh 发现两个 P1：`cross_domain_call` 在 triggers 里但 predicate 漏枚举；普通 `to=ops@example.com` 在 layered 模式下会被邮箱正则误拒。本轮已补 predicate 和 Gate4 routing 字段语义测试。
- 第三轮 xhigh 发现 routing 字段整值跳过过宽，可能藏入 AKIA/身份证/secret。本轮已收窄为只豁免低置信普通 routing 地址，高置信秘密仍扫描。
- 最终 xhigh 只读复审结论：当前没有 P0/P1 blocker，Gate2/Gate3/Gate4 baseline policy 对齐可以通过最终复审；剩余均为 P2/P3 长期增强项。

最终验证结果：
- `python -m pytest --collect-only -q -p no:cacheprovider`：收集 230 个测试点。
- `python -m pytest -q --basetemp pytest_tmp_final_p1_fixed -p no:cacheprovider`：通过，230 个测试点全绿。
- `python scripts\enrich_csab_gov_mini.py --check`：通过，bench YAML 元数据最新。
- `$env:PYTHONPATH='src'; python -m compileall -q src tests bench demo sdk scripts`：通过。
- `python -m bench.cli run --suite bench\cases\csab-gov-mini-seed.yaml --config configs\xa-guard.yaml`：290 条，pass_rate 1.0，ASR 0.0，FPR 0.0，Recall 1.0，P50/P95 37.93/62.53 ms。
- `$env:PYTHONPATH='src'; python scripts\verify_audit.py --path logs\audit\audit.jsonl`：verified 11773 records, 0 chain errors, 0 missing-field records。

未完成 / 客观限制：
- overlay 新增 Gate3 trigger 时，还没有强制要求同时新增 Gate2 risk 与 Gate4 capability；当前只是 baseline 层有自动一致性测试，后续应把这个检查接入 overlay merge。
- Gate4 legacy fallback regex 仍只是 `sensitive_patterns.yaml` 的子集；生产 layered 路径可用，但 fallback 注释/同源生成后续应处理。
- routing 字段高置信模式可继续调优，避免少数低风险通道名误报。
- 这轮仍没有完成真实客户端 HITL、OPA/Rego、approval token、Docker/gVisor 真执行、真实模型推理评测。

## 2026-06-02 +08:00 Codex 主 agent — Gate2/3/4 baseline 错位补齐

按用户要求“先把错位补上，别的先不动”，本轮只修前一轮侦察确认的 Gate2/Gate3/Gate4 baseline 明显错位；没有改 `bundle_sha` 语义，没有新增跨资源一致性校验，没有重构为统一 tool registry，也没有读取或维护 `implementation-notes.html`。

本次具体做了：
- 先按 TDD 补失败测试：`tests/unit/test_gate2.py` 覆盖 `post_url` 应为 yellow warn、`red_operation` 应为 red require_approval；`tests/unit/test_gate3.py` 覆盖 `shell` alias、`append_file`、`content_generation` 触发原有规则；`tests/unit/test_gate4.py` 覆盖 `delete_file`/`drop_table` 必须有显式 red capability。
- 修改 `policies/tool_risks.yaml`：补齐 `post_url: yellow`、`write_file: yellow`、`append_file: yellow`、`shell: red`、`red_operation: red`，保持 `exec_command/delete_file/drop_table` 为 red。
- 修改 `policies/tool_capabilities.yaml`：补齐 `write_file`、`append_file`、`shell`、`delete_file`、`drop_table`、`red_operation` 的能力、输入污点上限、输出污点和 risk_level，使 Gate4 不再对这些工具走默认 capability。
- 修改 `policies/enterprise-l3.yaml`：把 `shell` 加入 `GBT-22239-8.1.4.4` triggers；把 `append_file` 加入 `GBT-45654-A.2.3` triggers，并让 `content_generation` 也能被 predicate 命中；把 `exec_command/shell/delete_file/drop_table` 加入 `TC260-003-9.4` triggers，保留 `red_operation`。

验证结果：
- 先运行新增定向测试，确认红测失败在 `post_url` 被 Gate2 当 green allow。
- 修改后运行 `PYTHONPATH=src python -m pytest -q -p no:cacheprovider --basetemp pytest_tmp_run tests\unit\test_gate2.py tests\unit\test_gate3.py tests\unit\test_gate4.py -x --tb=short`：通过，71 个定向测试全绿。
- 运行 `PYTHONPATH=src python -m pytest -q -p no:cacheprovider --basetemp pytest_tmp_run tests\unit\test_layered_policy.py tests\test_pipeline_smoke.py tests\integration\test_bench_smoke.py tests\unit\test_bench_metrics.py -x --tb=short`：通过，34 个相关测试全绿。
- 运行 `PYTHONPATH=src python -m pytest -q -p no:cacheprovider --basetemp pytest_tmp_run`：全量 pytest 通过，211 个测试点全绿。
- 运行 `PYTHONPATH=src python -m bench.cli run --suite bench\cases\csab-gov-mini-seed.yaml --config configs\xa-guard.yaml`：290 条 pass_rate 1.0。
- 运行 `PYTHONPATH=src python scripts\validate_csab_gov_mini.py --strict`：cases=290 errors=0 warnings=0。
- 运行 `PYTHONPATH=src python scripts\verify_audit.py --path logs\audit\audit.jsonl`：verified 8278 records, 0 chain errors, 0 missing-field records。

未完成 / 客观限制：
- 尚未实现跨资源一致性校验；后续新增工具仍可能只改 Gate3 triggers 而漏改 Gate2/Gate4。
- 尚未修 `bundle_sha` 包含 rejected overlay 文件的问题。
- 尚未做统一 `tool_registry.yaml` 或自动生成 Gate2/Gate4 资源。
- 尚未补生产口径 `prefer_layered=true` 的专门 pipeline 测试；本轮只补 legacy 单文件路径和现有 layered/bench 回归。

## 2026-06-02 +08:00 Codex 主 agent — Gate2/3/4 baseline 对齐只读侦察

按用户要求，重点侦察 Gate2、Gate3、Gate4 以及相关 baseline 策略，目标是先给整理方案，不直接改策略代码。本轮没有读取或维护 `implementation-notes.html`，没有修改产品代码、策略 YAML 或测试。

本次具体做了：
- 使用 3 个只读 explorer 子 agent 并行侦察 Gate2、Gate3、Gate4/跨 gate baseline，均要求不改文件、不写日志。
- 本地读取 `status.md`、`AGENTS.md`、`configs/xa-guard.yaml`、`src/xa_guard/gates/gate2_plan.py`、`gate3_policy.py`、`gate4_taint.py`、`src/xa_guard/policy/layered.py`、`monotonicity.py`、`compiler.py`、`src/xa_guard/pipeline.py`、`src/xa_guard/server.py`、`src/xa_guard/types.py`、`src/xa_guard/gates/gate6_audit.py`、`policies/baseline_manifest.yaml`、`policies/enterprise-l3.yaml`、`policies/tool_risks.yaml`、`policies/tool_capabilities.yaml`、`policies/sensitive_patterns.yaml` 以及相关单元测试。
- 确认 Gate2/3/4 已共享 `LayeredPolicySource`，但共享的是 4 类资源入口，不是同一份“工具语义契约”。Gate3 的 30 条规则 trigger 已扩到大量政企/模型/训练/审计工具，而 Gate2/Gate4 baseline 工具元数据仍只覆盖少量演示工具。
- 发现当前最直接的不齐点：`post_url` 在 Gate4 `tool_capabilities.yaml` 是 `risk_level: yellow`，但 Gate2 `tool_risks.yaml` 未登记，Gate2 会按 unknown tool 默认 green；`delete_file`、`drop_table` 在 Gate2 是 red，但 Gate4 未登记 capability，会走默认 `input_max_taint=CONFIDENTIAL`。
- 发现 Gate3 规则自身也有 trigger/predicate 不一致：`GBT-22239-8.1.4.4` predicate 包含 `shell` 但 triggers 不含 `shell`；`GBT-45654-A.2.3` triggers 包含 `content_generation`，predicate 却只检查 `write_file`/`append_file`，且 `append_file` 不在 triggers。
- 发现 `TC260-003-9.4` 规则 trigger `red_operation` 且 predicate 依赖 `risk == 'red'`，但 `red_operation` 未登记 Gate2 risk，pipeline 真实运行会默认 green，除非外部手动设置 risk。
- 发现 `LayeredPolicySource` 的 `bundle_sha` 当前按 baseline + 所有 overlay 文件计算，包含之后被 monotonicity 拒绝的 overlay；这和“当前生效策略快照”的语义不完全一致。

本轮完成情况：
- 已完成只读侦察和方案准备。
- 未实现任何修复；未运行 pytest/bench；未改 baseline 文件、overlay 校验或 pipeline 逻辑。

下一步建议：
- 先做低风险 baseline 对齐：补齐 `tool_risks.yaml` 与 `tool_capabilities.yaml` 的同工具风险一致性，修正 Gate3 trigger/predicate 明显错位。
- 再抽象统一工具目录或一致性校验，避免 Gate3 新增 trigger 后 Gate2/Gate4 漏登记。
- 最后补生产口径测试：`prefer_layered=true` + 全局 `LayeredPolicySource` + pipeline 真实顺序下的跨 gate 行为。

## 2026-06-02 +08:00 主 agent（Opus 4.7） — Gate2/3/4 双层策略 + bundle_sha 审计

按用户要求把 Gate2/3/4 改造成 **baseline（项目自带国标兜底）+ overlay（企业动态注入）** 的双层结构，让 XA-Guard 能在保留根本性硬规则的前提下动态接入企业实际策略。

调研：派 3 个 sonnet 子 agent 并行 WebSearch，覆盖 (1) OPA bundles / Gatekeeper / AWS SCP / Istio 的双层模型，(2) Lakera / NeMo Guardrails / Cloudflare AI Gateway / Azure Content Safety / Google Model Armor / Cisco AI Defense / Palo Alto Prisma AIRS 的客户策略形态与基线锁定能力，(3) 配置叠加 / 单调性 / 热加载 / predicate 沙箱替代品。结论：**Google Model Armor 的 Floor Settings + Kubernetes Gatekeeper 的 Template+Constraint 分离 + AWS SCP 的 "Deny 不被 IAM Allow 推翻"** 是最贴合本项目的三个范式，OPA Rego 留作 M3 切换路径。

本次具体做了：
- 新增 `src/xa_guard/policy/layered.py` `LayeredPolicySource` 进程级单例：读 baseline manifest + 扫 overlay 目录 → 4 类资源（policy_rules / tool_risks / tool_capabilities / sensitive_patterns）合并 → 暴露给 Gate2/3/4 共享；计算 `bundle_sha = sha256(所有源文件字节)`；线程安全 atomic ref swap。
- 新增 `monotonicity.py` 强制 4 类红线（rule.id 命中 baseline / tool_risks 从严降到松 / `input_max_taint` 放宽 / sensitive_patterns 重复 baseline），违例的 overlay 整批拒绝并写到 `overlay_rejections`，baseline 永远不动。
- 新增 `predicate_safe.py`：baseline tier 走原 `compile_predicate`；overlay tier 必须过 AST 白名单（`evalidate` 优先；缺失时用内置 walker 校验 ast.Compare/BoolOp/Call(限白名单) 等节点），拒绝 lambda / `__import__` / 属性调用等不安全表达。
- 新增 `hot_reload.py` `OverlayWatcher`：`watchfiles` 监听 overlay/，触发 `LayeredPolicySource.reload()`，新 snapshot 通过原子引用切换，失败保留旧 snapshot 不中断服务。`watchfiles` 缺失时降级为 noop。
- 新增 `policies/baseline_manifest.yaml` 注册 4 类 baseline 文件；`policies/sensitive_patterns.yaml` 把 Gate4 硬编码正则提取为可审计资产；`policies/overlay/_template/` 给企业接入示例（manifest / policy / tool_risks / tool_capabilities / sensitive_patterns 五件套）。
- 改 `src/xa_guard/gates/gate2_plan.py` / `gate3_policy.py` / `gate4_taint.py` 加 `prefer_layered` 开关（default false，生产 true），三家 Gate 都从 `get_global_source()` 读合并视图；缺失时 fallback 到原单文件路径，确保旧单测零改动。
- 改 `src/xa_guard/types.py` `AuditRecord` 加 `gen_ai_policy_bundle_sha` 字段，`to_dict()` 同步加 `"gen_ai.policy.bundle_sha"` key。
- 改 `src/xa_guard/gates/gate6_audit.py` 在写 record 时从 `get_global_source()` 取当前 `bundle_sha` 贴上；监管可凭这个 SHA 回查事故时刻生效的策略快照。
- 改 `src/xa_guard/server.py` `build_pipeline()` 启动期 `_init_layered_policy()` 实例化单例 + 启动 `OverlayWatcher`；`configs/xa-guard.yaml` 新增 `gates.policy_layered` 块默认启用。
- 改 `pyproject.toml` 把 `evalidate>=2.0` + `watchfiles>=0.21` 放进新的 `[project.optional-dependencies] policy` extra；缺失时 layered 自动降级。
- 新增 `tests/unit/test_layered_policy.py` 21 个测试覆盖 baseline 加载、命名空间强制、覆盖企图拦截、tool_risks/capabilities 弱化拦截、纯追加路径、AST 白名单拒绝 `__import__`/`lambda`、bundle_sha 随文件变化、reload fail-safe。

验证（每一步留 stdout 证据）：
1. `PYTHONPATH=src python -m pytest -q` → **204 passed**（旧 183 + 新 21），0 失败。
2. `PYTHONPATH=src python -m bench.cli run --suite bench/cases/csab-gov-mini-seed.yaml --config configs/xa-guard.yaml` → **290 条 pass_rate 1.0**，7 个 dimension 子分数全部 1.0。
3. `PYTHONPATH=src python scripts/validate_csab_gov_mini.py --strict` → cases=290 errors=0 warnings=0。
4. `PYTHONPATH=src python scripts/verify_audit.py --path logs/audit/audit.jsonl` → verified 7031 records, 0 chain errors。
5. `tail -1 logs/audit/audit.jsonl | jq '."gen_ai.policy.bundle_sha"'` → `"ffedcd6820ca3eecc9fd7f65bb8acec9e3ff6fa3bd97125d810cd85475f96672"`，新字段已落盘。

设计决策（与用户的三次拍板）：
- 改造范围 = **三 Gate 全做**（不是只动 Gate3），sensitive_patterns 一并外置为 yaml
- overlay predicate eval = **evalidate AST 白名单**（不留 `eval` 给企业可写路径）
- 热加载 = **watchfiles + atomic ref swap**（带 fail-safe 回退）

未完成 / 客观限制：
- 当前环境没装 evalidate / watchfiles，代码走"内置 walker + 无文件监听"兜底；生产环境装上 `pip install -e .[policy]` 自动启用。
- baseline 仍是 Python 受限 `eval()`；M3 切 OPA Rego 时同时迁 baseline 与 overlay 到 `base/tenant/decision` 三层 Rego 包。
- `bundle_sha` 是文件字节哈希，不是 git sha；M4 国密阶段可叠加 SM2 签名 + TSA 时间戳形成完整 bundle 信任链。
- overlay 模板 `_template/` 不会被加载（前缀 `_` 跳过），实际企业接入时新建非下划线开头的子目录。

---

## 2026-06-02 +08:00 主 agent（Opus 4.7） — 把 290 条 mini 升级为可信评测资产

按用户要求把 `bench/cases/csab-gov-mini-seed.yaml` 从「裸列表」升级到「带 case_kind + 标准来源 + 去重 + 覆盖率 + schema 校验」的可审计资产。

本次具体做了：
- 新增 `bench/schema/csab-gov-mini.schema.json`：JSON Schema，约束每条 case 的必填字段（case_id 正则、case_kind 枚举、source_documents 至少 1 条），可供 IDE / 外部 lint 复用。
- 新增 `scripts/enrich_csab_gov_mini.py`：幂等地把 290 条样例补齐 `case_kind`（attack_case 193 / benign_control 76 / assurance_check 21）、`source_documents`（按 policy_refs 前缀映射到 GB/T 22239-2019 / GB/T 45654-2025 / TC260-003 / 网安法 / AIGC 标识办法；无 policy_refs 的按 dimension fallback）、稳定 16 位 `fingerprint`；并对原 YAML anchor 复用的 28 组重复 payload 注入 `variant_index`，让 290 条 fingerprint 全部唯一。`--check` 给 CI 用。
- 新增 `scripts/validate_csab_gov_mini.py`：必填字段 + 枚举 + ID/fingerprint 唯一性 + case_kind↔attack_type 一致性 + policy_refs 白名单（从 `policies/enterprise-l3.yaml` 加载，外加 9 个子条款 ID）+ metadata.total/dimensions 对账；并把覆盖率报告写到 `bench/.log/coverage.md`。`--strict` 把告警提为错误。
- 新增 `tests/test_csab_gov_mini_assets.py` 7 个测试，把 schema/dedup/coverage/幂等性钉在 CI 里。
- 改写 `bench/cases/csab-gov-mini-seed.yaml`：290 条全部带 `case_kind` + `source_documents` + `fingerprint`；metadata 新增 `case_kinds` 分布；标准引用合计 137 GB/T 22239-2019 / 148 GB/T 45654-2025 / 48 TC260-003 / 12 网安法 / 11 AIGC，覆盖 41 个 attack_type × 7 dimension。

验证（顺序固定，每一步留有 stdout 证据）：
1. `python scripts/enrich_csab_gov_mini.py` → 写入；再 `--check` → 幂等通过。
2. `python scripts/validate_csab_gov_mini.py --strict` → cases=290 errors=0 warnings=0；coverage.md 已刷新。
3. `PYTHONPATH=src python -m pytest` → 183 passed（含新增 7 个 mini 资产校验测试，旧 176 个全部不变）。
4. `PYTHONPATH=src python -m bench.cli run --suite bench/cases/csab-gov-mini-seed.yaml --config configs/xa-guard.yaml` → 290 条 pass_rate 1.0，7 个 dimension 子分数全部 1.0。

未完成 / 客观限制：
- `source_documents` 中 fallback 引用（无 policy_refs 的 benign 案例）只到「附录 A 数据安全」这个粒度，没有逐条人工对齐到「附录 A.1.x.y」级别。
- `variant_index` 解决了 fingerprint 碰撞，但部分 benign_compliant / risk_explanation / audit_required_red_tool 案例本质上仍是同一 payload 的复制；将来扩量应换样本而不是堆 variant。
- 真实模型链路 / Qwen3Guard 推理 / MCP E2E / Docker 沙箱 / approval_token 闭环等历史缺口与本次无关，仍未推进。

## 2026-06-02 +08:00 Codex 主 agent

按用户关于 Gate3、政企策略、国密标准和策略审核的问题，做了一轮只读核对并准备答复。本轮没有读取或维护 `implementation-notes.html`，没有修改产品代码逻辑。

本次具体做了：
- 读取 `status.md`、`src/xa_guard/gates/gate3_policy.py`、`policies/enterprise-l3.yaml`、`configs/xa-guard.yaml`、`docs/事实源.md`，确认 Gate3 当前为运行期加载 YAML 策略文件的 Python predicate 后端。
- 确认当前 `policies/enterprise-l3.yaml` 已有 30 条 seed 规则，覆盖等保 2.0、GB/T 45654-2025、TC260-003 相关的审批、阻断、告警和审计要求。
- 确认当前 `backend=rego` 仍未实现，OPA/Rego 属于后续增强；`gate6.hash_algo` 默认仍是 `sha256`，`enable_sm2_signature: false`，正式 SM3/SM2 国密证据链尚未闭环。
- 准备给用户说明：策略不应写死在业务代码里，应在仓库保留可审计默认策略与 schema/测试，同时支持运行期加载租户/环境策略；国密主要用于审计证据链、重要操作签名、传输/存储保护，不是所有 Gate3 predicate 都要“用国密”。

未完成 / 客观限制：
- 本轮只做问题解答准备，没有实现 OPA/Rego、审批令牌闭环、正式 SM2 签名、TSA 时间戳或国密 TLS。
- 未运行测试或 bench，因为未改实现代码。

## 2026-06-02 +08:00 主 agent（Opus 4.8）

按用户要求更新根目录 `status.md`。本轮只做状态核对与刷新，未改产品代码逻辑。

本次具体做了：
- 核对工作区事实：`git status` 显示 bench log / seed / policy / gate4 / 多个测试与 status/log 有未提交改动；最新提交为 `21045ea`（已回退 spotlighting 默认、标记 llamaguard map TODO）。
- 重新执行验证：`PYTHONPATH=src python -m pytest` 通过，176 个测试点全绿；`compileall` 通过；bench 290 条 pass_rate 100.0%，指标与上一轮一致（ASR 0、Recall 100%、FPR 0、CuP 100%、P50/P95 8.37/11.87ms）。
- `verify_audit.py` 对主日志通过，记录数从上一轮 1442 增长到 2691，0 链错误、0 缺字段。
- 复核模型环境：仍无项目 `.venv`，全局 Python 未装 `transformers`/`torch`/`huggingface_hub`，确认本轮 bench 仍是规则链路 + mock executor + 模型 fail-open 口径。
- 更新 `status.md`：刷新时间戳、测试点数（176）、审计记录数（2691），其余状态判断维持不变。

未完成 / 客观限制：
- 未重建 `.venv`、未复现真实 Qwen3Guard 推理；未推进 MCP E2E、OPA、Docker 真沙箱、审批令牌审计闭环等既有缺口。

## 2026-06-01 23:39 +08:00 Codex 主 agent

按用户要求先查看 `status.md`，并按指定流程派出多轮子 agent：第一轮 3 个 `gpt-5.5 medium` 子 agent 分别围绕等保 2.0 / GB/T 22239、GB/T 45654、TC260-003 做 web search 和事实源提炼；主 agent 随后用官方页面复核关键事实；第二轮 3 个 `gpt-5.5 medium` 子 agent 分别给出 Policy 规则候选、290 条 bench 生成矩阵、单测扩展建议。本轮没有读取或维护 `implementation-notes.html`。

本次具体做了：
- 读取 `status.md`、`AGENTS.md`、`policies/enterprise-l3.yaml`、`bench/cases/csab-gov-mini-seed.yaml`、Gate3/Gate4/bench runner 和相关测试，确认当前 Policy 为 10 条、bench 为 30 条 seed。
- web 核验官方事实源：GB/T 22239-2019 为 2019-05-10 发布、2019-12-01 实施的现行标准；GB/T 45654-2025 为 2025-04-25 发布、2025-11-01 实施的现行推荐性国标；TC260-003 为 TC260 于 2024-03-01 发布并提供 PDF 的技术文件；同时核对网络安全法日志留存不少于六个月、生成式 AI 暂行办法和 AI 生成合成内容标识相关官方口径。
- 先按 TDD 改测试制造红灯：`test_gate3.py` 期望 Policy 30 条并新增合规规则命中/未命中断言；`test_bench_smoke.py` 期望 CSAB-Gov-mini 290 条和 7 维度分布。
- 扩展 `policies/enterprise-l3.yaml` 到 30 条规则，新增日志留存、审计删除、备份、加密降级、CII 外联、关键岗位权限、职责隔离、扩展要求、等保测评证据、训练数据授权、robots 禁采、商业来源证明、个人/敏感个人信息、第三方模型备案、模型更新评估、标注职责隔离、未成年人保护、AI 标识、连续诱导违法输入等规则。
- 生成并写入 `bench/cases/csab-gov-mini-seed.yaml` 290 条样例：execution 60、data 50、content 60、supply_chain 25、compliance 50、interpretability 20、traceability 25。
- 根据 bench mismatch 补了最小实现和测试：旧越权规则纳入 `drop_table/admin_action`；写文件涉敏规则纳入 `手机号/secret_key/access_key`；Gate4 中文敏感词扫描纳入手机号、银行卡、医疗健康、金融账户、行踪轨迹、敏感个人信息。
- 更新测试：Gate3/Gate4 新增规则与敏感词单测；bench smoke 改为 290 条；AIBOM supply_chain 测试保留前 4 条 seed 决策断言并确认扩容到 25 条。
- 运行 bench 刷新 `bench/.log/last_results.json`、`last_report.json`、`report.html`，当前 290 条 pass_rate 100.0%、ASR 0.0%、Recall 100.0%、FPR 0.0%、CuP 100.0%、P50/P95 8.37/11.87ms。
- 更新 `status.md`：同步 Policy 30 条、CSAB-Gov-mini 290 条、最新 bench 指标、审计验链记录数和仍未完成的真实模型/MCP E2E/OPA/Docker/审批闭环等状态。

验证结果：
- `PYTHONPATH=src python -m pytest -q`：通过。
- `PYTHONPATH=src python -m compileall -q src tests bench demo sdk scripts`：通过。
- `PYTHONPATH=src python -m bench.cli run --suite bench/cases/csab-gov-mini-seed.yaml --config configs/xa-guard.yaml`：通过，290 条样例 exact pass。
- `PYTHONPATH=src python scripts\verify_audit.py --path logs\audit\audit.jsonl`：通过，1442 条记录，0 个链错误，0 条缺字段。

已完成：
- Policy DSL 已从 10 条扩到 30 条。
- CSAB-Gov-mini 已从 30 条扩到 290 条。
- 单测和集成 smoke 已随扩容更新。
- 本轮事实源核验、子 agent 产出、规则/样例/测试/status/log 维护均已完成。

未完成 / 客观限制：
- 当前 bench 仍是规则链路 + mock executor + 模型 fail-open 口径，不是真实 Qwen3Guard 推理，也不是 MCP E2E。
- 290 条是 mini/PoC 样例，不等于 GB/T 45654 完整题库规模；尚未实现自动覆盖率检查、case_kind、infra_error、audit delta 或组合 oracle。
- OPA/Rego、Docker/gVisor 真执行、真实客户端 HITL 弹窗、approval_token 审计闭环、国密正式链路仍未完成。

下一步建议：
- 把 290 条 YAML 进一步产品化：补 schema/coverage 校验和可重复生成脚本，避免手工维护风险。
- 推进 XA-Bench hardening：`case_kind`、显式 `infra_error`、audit delta、真实 audit completeness 和 MCP E2E harness。
- 统一模型环境，明确本机只跑规则链路或重建 `.venv` 跑真实 Qwen3Guard 指标。

## 2026-06-01 21:30 +08:00 Codex 主 agent

按用户要求继续工作并更新根目录 `status.md`。本轮没有读取或维护 `implementation-notes.html`。用户允许并行侦察后，派出 3 个 `gpt-5.5 medium` 子 agent 只读检查：代码/测试/配置状态、bench/审计状态、赛题/PRD 差距；主 agent 同时在本地运行验证和核对关键文件。

本次具体做了：
- 读取当前 `status.md`、`log.md`、`README.md`、`configs/xa-guard.yaml`、`pyproject.toml`、bench log、审计脚本、SDK、Gate2/Gate5、policy 和 metrics 相关文件。
- 确认当前工作区是 `main`，`git status --short` 初始为空。
- 重新执行验证：`PYTHONPATH=src python -m pytest -q` 通过，160 个测试点；`PYTHONPATH=src python -m compileall -q src tests bench demo sdk scripts` 通过。
- 重新执行 seed bench：`PYTHONPATH=src python -m bench.cli run --suite bench/cases/csab-gov-mini-seed.yaml --config configs/xa-guard.yaml` 通过，刷新 `bench/.log/last_results.json`、`last_report.json`、`report.html`。
- 重新执行审计验链：`PYTHONPATH=src python scripts\verify_audit.py --path logs\audit\audit.jsonl` 通过，231 条记录，0 个链错误，0 条缺字段。
- 核对当前 Python 环境：全局 `python` 是 3.12.10，但项目根目录没有 `.venv`；当前环境未安装 `transformers`、`torch`、`huggingface_hub`。
- 直接构造 Gate1 detector 检查：`rule` detector 存在；`model:qwen3guard` 后端存在但 `is_ready=False`，说明当前 bench 是模型 fail-open 后的规则链路，不是 Qwen3Guard 真实推理。
- 更新 `status.md`：纠正旧状态中“Spotlighting 默认开启”“当前可复现为真实 Qwen CPU 推理”等不符合当前工作区事实的表述；同步最新 bench 指标 P50/P95 2.13/6.55ms，并明确这只是规则 pipeline + mock executor + 模型 fail-open 延迟。

已完成：
- `status.md` 已按当前仓库状态重写为最新看板，覆盖赛题 4 个方向、可用能力、空壳/占位、最新验证结果、PRD 差距和下一步优先级。
- 明确保留 demo 边界：30 条 seed 不是 290 条，`audit_completeness=1.0` 是固定占位，bench 普通 case 使用 mock executor，供应链 case 走简化路径，CoT faithfulness / 国密 / Docker / OPA / 真实客户端 HITL 均未完成。

未完成 / 客观限制：
- 本轮没有修改产品代码逻辑。
- 没有重建 `.venv` 或安装模型依赖，也没有复现 Qwen3Guard 真实推理。
- 没有修 XA-Bench 的 `case_kind`、`infra_error`、audit delta、真实 MCP E2E harness 等 hardening 缺口。
- 没有更新 README 中可能偏满的能力表述；本轮只按用户要求更新 `status.md` 并维护根日志。

下一步建议：
- 先统一环境：重建 `.venv` 并安装 `xa-guard[bench,model]`，或明确当前开发机只跑规则链路。
- 决定是否把 `spotlighting.enabled` 改为 `true`，改后重新跑测试和 bench。
- 开始实现 XA-Bench hardening：`case_kind`、显式 `infra_error`、组合 oracle、审计 delta 和 MCP E2E harness。

## 2026-05-31 20:45 +08:00 Codex 主 agent

按用户要求继续推进 Gate1 真实 Guard 模型阶段，未切回或修改 `main`，继续在 `codex/gate1-model-integration` 分支开发。未删除 benchmark / audit 数据；`bench/.log/*` 是按真实 bench 运行刷新。

本次具体做了：
- 修正 `src/xa_guard/detectors/backends/qwen3guard.py`：Qwen3Guard-Gen 不再按普通 `text-classification` pipeline 接入，改为官方生成式流程 `AutoModelForCausalLM` + `apply_chat_template` + `generate`，解析 `Safety:` 和 `Categories:`。
- 新增真实后端：`promptguard.py`（PromptGuard2 sequence classification）、`shieldlm.py`（ShieldLM 生成式安全检测）、`llamaguard.py`（Llama Guard 生成式安全检测）。
- 更新 `src/xa_guard/detectors/backends/__init__.py`：注册 `qwen3guard`、`promptguard`、`shieldlm`、`llamaguard` 四个真实后端，移除旧占位类。
- 更新 `src/xa_guard/detectors/fusion.py`：补充模型类通用 deny 类目 `unsafe`、`political_sensitive`、`ops_destructive`、`classified_exfil`、`social_engineering`。
- 更新 `configs/xa-guard.yaml`：默认启用真实 Qwen3Guard-Gen-0.6B（`dry_run: false`），保留规则 detector 和 fail-open；PromptGuard2 / ShieldLM / Llama Guard 以注释配置保留，避免无授权或超资源环境阻塞启动。
- 新增类目映射：`policies/qwen3guard_category_map.yaml`、`policies/promptguard_category_map.yaml`、`policies/llamaguard_category_map.yaml`。
- 新增验证脚本 `scripts/probe_gate1_models.py`：支持模型元数据、snapshot 下载、直接 backend 推理、RSS 和 latency 粗测，不修改 XA-Bench case。
- 更新 `pyproject.toml` 的 `model` extra：补 `huggingface-hub`、`safetensors`、`sentencepiece`、`protobuf`、`psutil`。
- 新增 `docs/gate1-real-model-verification.md`：记录真实模型矩阵、下载状态、资源占用、benchmark 和 blocker。

环境与依赖：
- 继续使用项目 `.venv`，Python 3.12.10。
- 已安装 model 依赖到 `.venv`：`torch 2.12.0+cpu`、`transformers 5.9.0`、`accelerate 1.13.0`、`huggingface-hub 1.17.0` 等。
- 本机 `nvidia-smi` 能看到 RTX 5070 Laptop 8GB VRAM，但当前 PyTorch 是 CPU 版，`torch.cuda.is_available() == False`，所以本轮真实推理为 CPU。

模型下载与验证：
- Qwen3Guard-Gen-0.6B：已下载，模型声明大小 1.415GB，实际 HF cache 文件约 1.52GB，缓存位置 `C:\Users\Enfur\.cache\huggingface\hub\models--Qwen--Qwen3Guard-Gen-0.6B\snapshots\fada3b2f655b89601929198343c94cd2f64d93cc`。
- Qwen3Guard 真实推理成功：加载约 5.98s，加载后 RSS 约 3275.67MB；单条 CPU 推理约 705-1101ms。Unsafe 样例可产出 `shell_dangerous`；Controversial 默认 `score=0.4`，低于 Gate1 阈值，避免把正常查询误拦。
- PromptGuard2：后端已实现，但 `meta-llama/Llama-Prompt-Guard-2-86M` 为 gated repo；无 `HF_TOKEN` / 未接受许可时 snapshot 和 `config.json` 均 401。fail-open 验证通过。
- Llama Guard 3 1B：后端已实现，但 `meta-llama/Llama-Guard-3-1B` 为 gated repo；无 `HF_TOKEN` / 未接受许可时 snapshot 和 `config.json` 均 401。fail-open 验证通过。
- ShieldLM-14B-qwen：后端已实现，模型元数据可读，权重约 26.391GB；本机 CPU 版 torch + 32GB RAM / 8GB VRAM 不适合直接加载，本轮跳过加载以避免 OOM。建议 GPU 量化或远程推理。

验证结果：
- `PYTHONPATH=src .\.venv\Scripts\python.exe -m compileall -q src tests bench demo sdk scripts`：通过。
- `PYTHONPATH=src .\.venv\Scripts\python.exe -m pytest tests/unit/test_gate1_detectors.py tests/unit/test_gate1.py -q`：通过，51 个 Gate1 测试。
- `PYTHONPATH=src .\.venv\Scripts\python.exe -m pytest -q`：通过，160 个测试点。
- 真实 Qwen Gate1 直接探针：正常 CPU 查询 ALLOW；`How can I make a bomb?` 由 Qwen 输出 `Unsafe/Violent` 并 DENY；英文 jailbreak 仍由规则层 DENY。
- PromptGuard2 / LlamaGuard / ShieldLM fail-open 直接探针：模型 unavailable 时 Gate1 不崩溃，整体 ALLOW，保留 fallback 语义。
- `PYTHONPATH=src .\.venv\Scripts\python.exe -m bench.cli run --suite bench/cases/csab-gov-mini-seed.yaml --config configs/xa-guard.yaml`：真实 Qwen 配置跑通，30 条 seed pass_rate 96.67%，ASR 0，Recall 100%，FPR 0，CuP 100%，Latency P50/P95 775.5/3921.01ms。
- 失败 case 没有隐藏：仍只有既有 `DATA-003`，期望 allow，实际 warn，根因是 `send_notification` yellow 工具语义，不是模型新增回归。
- `PYTHONPATH=src .\.venv\Scripts\python.exe scripts\verify_audit.py --path logs\audit\audit.jsonl`：通过，146 条记录，0 个链错误，0 条缺字段。

未完成 / 客观限制：
- 当前 Windows `.venv` 安装的是 CPU 版 PyTorch；没有完成 CUDA 推理验证。Qwen3Guard-0.6B CPU 延迟明显高于 PRD 同步预算。
- PromptGuard2 和 Llama Guard 需要 Meta gated 模型访问授权和 `HF_TOKEN`，当前环境无法下载真实权重。
- ShieldLM-14B 原精度不适合本机直接跑；需 4/8-bit 量化、GPU 环境或远程推理服务。
- 还没有跑 Qwen3Guard 4B/8B，也没有做 290 条 bench 或 adaptive attack。

下一步建议：
- 配置 CUDA 可用 PyTorch 或迁移到 Linux/CUDA 环境，复测 Qwen3Guard-0.6B GPU latency。
- 接受 Meta license 并设置 `HF_TOKEN` 后重跑 PromptGuard2 / Llama Guard 3 1B 下载与推理。
- 对 ShieldLM 采用远程异步可解释层或 4-bit 量化方案，不建议放入 Gate1 同步主链路。

## 2026-05-31 19:19 +08:00 Codex 主 agent

按用户要求先从 GitHub 克隆仓库到 `C:\Users\Enfur\agent_safety`，没有在 `main` 上开发，已创建并切换到 `codex/gate1-model-integration` 分支。先阅读了 `docs/gate1-模型接入与微调要求.md`、`docs/产品架构.md`、`docs/PRD.md`、`status.md` 和 Gate1 / detector / pipeline 现有代码，再做最小模型接入。未读取或维护 `implementation-notes.html`。

本次具体做了：
- 新增 `src/xa_guard/detectors/backends/qwen3guard.py`：实现 `Qwen3GuardBackend`，支持真实 `transformers.pipeline("text-classification")` 惰性加载，缺依赖/缺权重时由 `ModelDetector` fail-open；同时提供显式 `dry_run` 模式，用于无权重环境验证 Gate1 模型调用链。
- 更新 `src/xa_guard/detectors/backends/__init__.py`：把 `qwen3guard` 从占位类替换为真实后端注册；保留 `shieldlm`、`promptguard`、`llamaguard` 占位。
- 新增 `policies/qwen3guard_category_map.yaml`：记录 Qwen3Guard 原生类目到 XA-Guard 统一类目的映射。
- 更新 `src/xa_guard/gates/gate1_input.py`：支持 `category_map_file`，把 `model_path/device/dry_run/threshold/category_map` 透传给 backend options；对纯 assistant history 场景设置 `DetectionInput.origin="assistant"`，避免模型 PII label 破坏既有 WARN 降级语义。
- 更新 `configs/xa-guard.yaml`：默认保留规则 detector，同时启用 `model_qwen` dry-run 后端和 Spotlighting。真实模型上线时只需安装 `xa-guard[model]`、准备权重并将 `dry_run` 改为 `false`。
- 更新 `pyproject.toml`：新增 `model` optional extra（`transformers`、`torch`、`accelerate`），`all` extra 包含 model。
- 更新 `tests/unit/test_gate1_detectors.py`：补 Qwen3Guard dry-run 模型链路、配置加载、assistant PII 降级回归测试。
- 按用户纠偏，未继续污染全局 `Python314`；用 winget 安装用户级 Python 3.12.10，并在项目内创建 `.venv`，所有依赖和测试都在 `.venv` 内执行。

验证结果：
- `.\.venv\Scripts\python.exe --version`：Python 3.12.10。
- `python -m pip show pytest`（全局 Python314）：未安装 pytest，确认本轮测试依赖未落到全局 Python314。
- `PYTHONPATH=src .\.venv\Scripts\python.exe -m pytest tests/unit/test_gate1_detectors.py tests/unit/test_gate1.py -q`：通过，51 个 gate1 测试全绿。
- `PYTHONPATH=src .\.venv\Scripts\python.exe -m pytest -q`：通过，160 个测试点全绿。
- `.\.venv\Scripts\python.exe -m compileall -q src tests bench demo sdk`：通过。
- 使用 `configs/xa-guard.yaml` 构建 pipeline 并直接调用 Gate1：`rule` 与 `model:qwen3guard` 都 available，dry-run 模型 label 参与 fusion，`ignore previous instructions` 被 DENY。
- `PYTHONPATH=src .\.venv\Scripts\python.exe -m xa_guard.server --help`：CLI 可加载并显示参数。
- `PYTHONPATH=src .\.venv\Scripts\python.exe -m bench.cli run --suite bench/cases/csab-gov-mini-seed.yaml --config configs/xa-guard.yaml`：通过运行，30 条 seed pass_rate 96.67%，ASR 0，Recall 100%，FPR 0，CuP 100%，Latency P50/P95 1.38/3.98 ms；仍只有既有 `DATA-003` exact mismatch。
- `PYTHONPATH=src .\.venv\Scripts\python.exe scripts\verify_audit.py --path logs\audit\audit.jsonl`：通过，120 条记录，0 个链错误，0 条缺字段。

已完成：
- Gate1 已有可注册、可配置、可调用的 Qwen3Guard 后端，模型接入链路能在无真实权重环境跑通。
- 规则层 fallback 仍保留，模型不可用时仍 fail-open，不阻塞 pipeline 启动和现有规则判断。
- Spotlighting 已在默认配置开启，配合 Qwen dry-run 进入当前 Gate1 编排。
- 项目内 `.venv` 已建立，后续开发/测试应继续使用 Python 3.12 虚拟环境。

未完成 / 客观限制：
- 本轮没有下载 Qwen3Guard 真实权重，也没有安装 `xa-guard[model]`；当前默认配置里的模型是 dry-run wiring，不代表真实 Qwen3Guard 推理效果。
- 没有完成官方 Qwen3Guard 28 类完整类目核对；`qwen3guard_category_map.yaml` 是基于现有文档的工程映射起点。
- 没有做微调、Recall@FPR 或 adaptive attack 评测；bench 仍是 30 条 seed regression，不是 PRD 290 条。
- `DATA-003` 仍是既有 exact mismatch：`send_notification` yellow 工具实际 WARN，期望 allow；指标上仍按非阻断处理。

下一步建议：
- 安装 `xa-guard[model]` 后，把 `dry_run: false`，用本地或镜像权重跑 Qwen3Guard-Gen-0.6B 真实零样本对比。
- 核对官方 Qwen3Guard 模型卡完整类目，更新 `policies/qwen3guard_category_map.yaml`。
- 把 30 条 seed 的规则版 vs Qwen3Guard 真实模型逐条差异写成报告，再决定是否默认开启真实模型或只作为旁路。

## 2026-05-31 14:49 +08:00 Codex 主 agent

按用户要求在 `main` 上审查仓库现状，围绕赛题要求为 hack / red-team 组员设计可接入 XA-Guard MCP 防护栏的提交规范和 XA-Bench 对抗测试规则。未读取或维护 `implementation-notes.html`。

本次具体做了：
- 派出 5 个 `gpt-5.5 medium` 子 agent 并行只读审查：赛题约束、现有 bench schema、MCP 可测试接口、对抗规则设计、独立事实复核。主 agent 同时本地读取官方赛题 PDF、事实源、PRD、核心架构、bench、pipeline、proxy 和测试。
- 使用 `pypdf` 抽取并核对官方赛题 PDF。确认官方方向 4 要求支持攻击复现、问题定位、效果验证和持续优化；攻击样例、测试数据说明、评测脚本和审计日志样例属于可选补充材料。
- 新增 `docs/HACK-BENCH-组员提交规范.md`：定义组员任务边界、taxonomy、`attack_case / benign_control / assurance_check / exploratory_finding` 四类提交、`automated / fixture_extension / manual_exploration` 三层验证、surface、oracle、严重性、去重、安全红线和提交流程。
- 新增 `docs/XA-Bench-对抗测试规则.md`：区分当前 v0.1 已实现口径和 v0.2 必须 harden 的目标，明确 `pipeline_harness / mcp_stdio / protocol_probe / aibom_rating / audit_verify / manual_client` 的证据边界。
- 新增机器可校验 schema `bench/schema/hack-submission.schema.json` 和 runner-compatible 模板 `bench/cases/hack-submission-template.yaml`。模板包含一个当前 loader 可读的自动化 case、一个 MCP stdio fixture extension、一个真实 IDE 手工验证记录。
- 修订文档索引和维护入口：`docs/README.md`、根 `README.md`、`docs/PRD.md`、`docs/事实源.md`、`docs/产品架构.md`、`docs/项目总览.md`、`docs/tutorials/MCP零基础上手.md`、文献库 INDEX、产品形态对比和 AgentDojo 导读。旧 HTML 留痕入口改为根目录 `log.md` / `status.md`。
- 纠偏关键事实：国标应拒答题库是“总规模 ≥ 500 且每类 ≥ 20”，340 只是逐类下限相加；XA-Bench 当前只有 30 条 seed regression，290 条是 PRD PoC 目标；Trae 展示基础 MCP / fallback，真实 elicitation 弹窗使用明确支持该能力的客户端。
- 同步 Gate1 文档主路线：从 PromptGuard 中文微调主线改为“规则 + Spotlighting + Qwen3Guard”，PromptGuard 2 保留英文 / 国际对照用途。
- 更新 `status.md`：记录新增规则工件，并补充 bench 可信度限制、MCP E2E 缺口、供应链简化路径、interpretability smoke 边界和下一步 hardening 优先级。

验证结果：
- `PYTHONPATH=src python -m pytest -q`：通过，157 个测试点全绿。
- JSON Schema 自检和模板校验通过：`hack submission schema: ok`。
- `PYTHONPATH=src python -c "from bench.runner import load_cases; ..."` 成功读取模板：`runner-compatible cases=1`，首条为 `HACK-D2-EXEC-0001 deny`。
- Markdown 相对链接扫描通过：`missing_relative_links=0`。
- `git diff --check` 通过，无空白错误；仅有 Windows 工作区既有 LF -> CRLF 提示。

已完成：
- hack 组员现在有明显、可执行、不会把 demo 能力夸大的提交规范。
- bench 维护者现在有明确的接入层、oracle、指标口径和演进规则。
- 提交格式已有机器 schema 和当前 runner 可读取的模板。
- 核心文档中的 290 / 30、500 / 340、Trae HITL、Gate1 主路线和旧 HTML 留痕入口已完成纠偏。

未完成 / 客观限制：
- 本轮没有改 `bench.runner` 和 `bench.metrics` 逻辑。`case_kind` 分桶、显式 `infra_error`、taint / rule hit / audit assertion、真实 audit completeness 仍是下一轮实现任务。
- 本轮没有新增真实 MCP stdio hack harness、多步工具链 harness 或 IDE 自动化测试。
- 还没有收集组员提交的第一批真实 candidate；模板里的内容是格式示例。
- 真实客户端 HITL UI、真实 Docker/gVisor、正式 SM2 + TSA、OPA Rego、真实模型推理仍未完成。

下一步建议：
- 先实现 XA-Bench v0.2 hardening：`case_kind` 分桶、异常显式失败、组合 oracle 和 audit 验链。
- 按新模板给 hack 组员分派第一批任务，优先覆盖 runner 异常一致性、审批拒绝后零执行、审计篡改和多步污染链。
- 建立独立 `mcp_stdio` harness，再把可稳定复现的 MCP fixture 晋升为自动化 regression。

## 2026-05-28 18:44 +08:00 Codex 主 agent

按用户要求继续派出 4 个子 agent 并行处理审计归档、HITL、EXEC-004 优先级、AIBOM 升级；主 agent 审查合理性、补安全边角、执行真实归档并更新状态。未读取或维护 `implementation-notes.html`。

本次具体做了：
- 新增审计归档入口：`src/xa_guard/audit/archive.py` 和 `scripts/archive_audit.py`。归档会先统计 verify 结果，再移动原始 JSONL 到 `logs/audit/archive/`，写 manifest，不重写旧链。
- 执行真实归档：`logs/audit/audit.jsonl` 被归档为 `logs/audit/archive/audit-20260528T104349214385Z.jsonl`，manifest 记录旧日志 1146 条、34 个链错误、首错第 401 行；新的 `logs/audit/audit.jsonl` 为空文件，verify 0 错。
- 修 EXEC-004：pipeline 改为 Gate1 立即短路，Gate2/Gate4/Gate3 先聚合，再按 `ctx.final_decision` 阻断；这样 Gate3 越权 DENY 能覆盖 Gate2 red 工具 REQUIRE_APPROVAL，admin/ops 的 red 操作仍需审批。
- 补 HITL toy 协议 probe 和最小 upstream 接入：`demo/elicitation_probe_server.py`、`scripts/probe_mcp_elicitation.py`、`docs/tutorials/HITL-elicitation-toy-probe.md`；`proxy/upstream.py` 在客户端声明 elicitation 时请求 approve/reject。
- 审查并修正 HITL approve 后路径：子 agent 初版 approve 后直接调用 downstream，会绕过 Gate5 和出向审计；主 agent 改为 `pipeline.run_after_approval()`，批准后仍跑 Gate5、executor、Gate4(out)、Gate6。
- AIBOM 升级：新增 CycloneDX-like 导出、AIBOM drift 比较、本地 artifact/file URL/zip/tar 解包、sha256 provenance、typosquat 启发式；远程 http(s) 不下载，只标记需要离线拉取。
- 补 AIBOM archive traversal 防护：zip/tar 解包前校验 member path，拒绝 `../escape.py` 这类路径穿越。
- 刷新 `bench/.log/last_results.json`、`last_report.json`、`report.html`，并同步 README/status。

验证结果：
- `PYTHONPATH=src python -m pytest -q`：通过，全量测试绿。
- 30 条 seed bench（临时 audit 目录）：pass_rate 96.67%，ASR 0，Recall 100%，FPR 0，CuP 100%；execution_safety 8/8，supply_chain 4/4。
- `PYTHONPATH=src python scripts/probe_mcp_elicitation.py`：触发 1 次 toy elicitation event，返回 `approved: hello`。
- `PYTHONPATH=src python scripts/probe_mcp_elicitation.py --reject`：触发 1 次 toy elicitation event，返回 `rejected`。
- `PYTHONPATH=src python scripts/verify_audit.py --path logs/audit/audit.jsonl`：通过，当前新主日志 35 条记录、0 个链错误、0 条缺字段。
- `PYTHONPATH=src python scripts/verify_audit.py --path <temp-bench-audit>/audit.jsonl`：通过，26 条新写入记录 0 个链错误、0 条缺字段。

已完成：
- 旧审计主日志已归档，新主日志从空链开始。
- EXEC-004 已 exact pass。
- AIBOM 从本地静态扫描 MVP 升级到可导出/可比较/可校验 sha256 的离线闭环。
- HITL 已完成 toy MCP 协议 probe 和 upstream 最小接入，approve 后不再绕过 Gate5/审计。

未完成 / 客观限制：
- 还没有 Cursor / Claude Code / Codex 真实 UI 弹窗实测记录，不能宣称真实客户端弹窗已跑通。
- HITL 审批理由、审批人、approval_token 尚未进入审计字段。
- AIBOM 没有联网下载远程包、外部信誉库、真实签名体系、Sigstore/TUF，也没有 CycloneDX schema 校验。
- bench 仍有 `DATA-003` exact mismatch：预期 allow，实际 warn；这是 yellow 通知工具语义，指标上按非阻断处理。

下一步建议：
- 做真实客户端 HITL 弹窗实测并记录证据。
- 把 approval_token / approver / reason 写入 Gate6 审计。
- AIBOM 接 CycloneDX schema 校验和签名体系。
- 扩 policy 到 30 条、扩 CSAB-Gov-mini 到 290 条。

## 2026-05-28 18:25 +08:00 Codex 主 agent

按用户要求先派出 4 个子 agent 并行调查/修复 bench、audit、AIBOM、HITL 四条线；主 agent 负责评估合理性、集成、验证和更新状态。未读取或维护 `implementation-notes.html`。

本次具体做了：
- 对比旧 `bench/.log/last_results.json`，定位 10 个失败 case：`EXEC-004`、`EXEC-008`、`DATA-003`、`DATA-004`、`CONT-002`、`SCM-001/002/004`、`COMP-002`、`INTP-001`。
- 修复 bench/规则退化中的合理项：`restart_service` 纳入重要操作审批；RAG `[ADMIN_OVERRIDE]` 从硬拒降为 WARN；assistant 历史里的 `/etc/passwd` 从硬拒降为 WARN；新增“家庭住址/家庭地址”隐私拒答模式；跨域 body 含“内部”触发 WARN；FPR/CuP 指标把 WARN 作为非阻断处理，但 exact pass 仍保留 allow/warn 差异。
- 补方向 3 AIBOM MVP：Python AST 扫描危险 import/API，JSON/YAML 元数据扫描，requirements/pyproject/METADATA 依赖风险解析，A/B/C/D/F 评级和具体理由；bench 的 `install_plugin` seed 通过薄接入映射 A/B=allow、C=warn、D/F=deny。
- 修审计写入侧分叉根因：`ChainStore.append()` 增加文件锁，并在锁内重新恢复最新 `record_hash` 后再追加，避免多个 ChainStore 实例并行写同一 JSONL 时使用旧 `_last_hash`。
- 核查 HITL：确认当前 `Gate2` 只返回 `REQUIRE_APPROVAL` / fallback，`proxy/upstream.py` 未接真实 MCP elicitation；本轮不写假支持，后续需先用支持 elicitation 的客户端做 toy 实测。
- 同步 README seed 指标、刷新 `bench/.log/last_results.json` / `last_report.json` / `report.html`，并更新根目录 `status.md`。

验证结果：
- `PYTHONPATH=src python -m pytest -q`：通过，全量测试绿。
- 用临时 audit 目录跑 30 条 seed bench：pass_rate 93.33%，ASR 0，Recall 100%，FPR 0，CuP 100%，supply_chain 4/4。
- `PYTHONPATH=src python scripts/verify_audit.py --path <temp-bench-audit>/audit.jsonl`：通过，26 条新写入记录 0 个链错误，0 条缺字段。
- `PYTHONPATH=src python scripts/verify_audit.py --path logs/audit/audit.jsonl`：仍失败，969 条历史记录中 34 个 hash_prev 链错误，0 条缺字段。

已完成：
- bench 退化主要修复完成，README/status/bench log 与新实测同步。
- AIBOM 不再是 stub，方向 3 seed 从 25% 变为 100%。
- 审计链未来写入分叉问题已修，新写入可验。

未完成 / 客观限制：
- 历史 `logs/audit/audit.jsonl` 已经分叉，不能通过改代码“修复”旧链；应归档/轮转，而不是重写伪造历史。
- `EXEC-004` 仍是 exact mismatch：期望 deny，实际 require_approval，根因是 Gate2 red 工具先短路，Gate3 越权 deny 没机会执行；需要单独设计 Gate2/Gate3 聚合优先级。
- `DATA-003` 仍是 exact mismatch：期望 allow，实际 warn；这是 yellow 通知工具的产品语义，指标上已按非阻断处理。
- HITL 真实 elicitation 未接入；需要先用 Cursor/Claude Code/Codex 等支持客户端实测 toy server，再改 `proxy/upstream.py`。
- AIBOM 仍是本地静态扫描 MVP，未做 CycloneDX/AIBOM 正式导出、签名校验、远程包解包、信誉库和漂移监测。

下一步建议：
- 先轮转/归档旧 audit 主日志，从修复后的新链开始保留证据。
- 决定 `EXEC-004` 的 Gate2/Gate3 优先级策略。
- 做真实 MCP elicitation toy 实测，再接入 XA-Guard upstream。
- 将 AIBOM MVP 扩展到 CycloneDX、签名和漂移监测。

## 2026-05-27 23:41 +08:00 Codex 主 agent

维护根目录 `status.md`，按 AGENTS.md 要求没有读取或维护 `implementation-notes.html`。

本次具体做了：
- 读取 `AGENTS.md`、`README.md`、`docs/PRD.md`、`docs/事实源.md`、`docs/产品架构.md`、`pyproject.toml`、根目录 `log.md/status.md`，并检查 `src/`、`bench/`、`sdk/`、`demo/`、`frontend/`、`tests/`、`policies/`、`scripts/` 的文件结构与 TODO/stub/NotImplemented 标记。
- 重点核对赛题 4 个方向与当前仓库实现：输入攻击识别、工具调用/任务执行安全、插件供应链、评测审计溯源。
- 重新执行验证：
  - `PYTHONPATH=src python -m pytest -q` 通过，测试输出显示 93 个测试点全绿。
  - `PYTHONPATH=src python -m bench.cli run --suite bench/cases/csab-gov-mini-seed.yaml --config configs/xa-guard.yaml` 可运行，最新 pass_rate 为 66.67%、ASR 为 22.73%、FPR 为 12.5%、Recall 为 77.27%、CuP 为 87.5%。
  - `PYTHONPATH=src python scripts/verify_audit.py --path logs/audit/audit.jsonl` 未通过，661 条记录中有 34 个 hash_prev 链错误，0 条缺字段。
- 写入新的 `status.md`，把仓库当前状态定位为 demo MVP / M1 末到 M2 前可运行骨架，并列出主要空壳：SDK、AIBOM、MCP elicitation、Streamable HTTP、OPA/Rego、Docker/gVisor、国密证据链、CoT 忠实度、290 用例评测、比赛 PDF/视频交付物。

已完成：
- `status.md` 从空文件变为当前仓库状态看板，内容贴合 XA-202620 赛题方向和 PRD 目标。
- `log.md` 顶部追加本次客观工作记录。

未完成 / 后续应做：
- 没有修改代码逻辑。
- 没有修 bench 指标退化、审计验链失败、AIBOM stub、SDK stub 等问题。
- 下一步建议优先排查 `bench/.log/last_results.json` 中导致 FPR 12.5% 和 data_safety CuP 0 的具体 case，并定位 `logs/audit/audit.jsonl` 第 401 行附近开始的链错误。

## 2026-05-27 主 agent（Opus 4.7）

派 3 个 sonnet 子 agent 并行修 pipeline 三处 bug：

1. **pipeline.py REQUIRE_APPROVAL 不阻断 executor** → 在 inbound 循环里把 `Decision.DENY` 短路条件扩展到 `(DENY, REQUIRE_APPROVAL)`，并把返回的 `final_decision` 改为 `result.decision`。更新模块 docstring。新增 `test_pipeline_blocks_executor_on_require_approval`。
2. **types.py GateContext.append WARN 被吞成 ALLOW** → WARN 分支补写 `self.final_decision = Decision.WARN`，保持优先级 DENY > REQUIRE_APPROVAL > WARN > ALLOW。主 agent 二次审核时发现 REQUIRE_APPROVAL 守卫只看 ALLOW 会被前面 WARN 卡住，把守卫扩到 `(ALLOW, WARN)`。新增 `tests/unit/test_types_warn.py`。
3. **audit log 缺 final_decision** → `AuditRecord` 加 `gen_ai_decision_final` / `gen_ai_decision_final_reason` 两字段并写入 `to_dict()` 的 OTel key；`Gate6Audit.evaluate` 从 `ctx.final_decision.value` / `ctx.final_reason` 取值。新增 `test_audit_record_carries_final_decision`。

审核 git diff：4 个源文件 + 2 个测试文件，共 +89 / −1086（todo.md 之前已删）。`pytest tests/` **93 passed**。

README 同步：测试数 87 → 93。审计字段从 14 增到 16，verify_audit 脚本未改（不在本次范围）。

子模块工作日志已由子 agent 各自写入：
- `src/xa_guard/.log/2026-05-27_require_approval_fix.md`
- `src/xa_guard/.log/2026-05-27_warn_fix.md`
- `src/xa_guard/audit/.log/2026-05-27_final_decision.md`

未做：commit、verify_audit 脚本同步 16 字段。
