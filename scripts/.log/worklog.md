# scripts 工作日志

## 2026-07-15 Reference core P0
- 全新 volume 跑 core，定位 PostgreSQL 恢复后未等待 Keycloak，补 discovery readiness 后 7/7 通过；未运行 long/keys/performance，也未封存最终 evidence。

## 2026-07-05 R4 性能验收复跑
- 复跑 `test_l3_performance_benchmark.py`、进程内 500、HTTP 10x500 与 HTTP 20x500 容量边界。
- 10x500 两项达 PRD medium；20 session P95 483.732ms 超标，仅记 LIMIT。
- 证据落 `docs/evidence/l3-r4-20260705-current/`，未改脚本或测试。

## 2026-06-20 本轮 L3 静态实现
- 完成双 500、faithfulness、LangChain / LangGraph、Trae / gVisor / OPA、AIBOM 外部交换的静态实现与统一 verifier 收敛，并补齐完整验收说明和 Apache-2.0 `LICENSE`。
- 最终轻量 pytest 合并运行 `121 passed`，统一 verifier `11/11 sections PASS`；未运行全仓 pytest，也未运行真实 LLM、Docker、gVisor、OPA 或 Trae，相关实机和端到端证据仍待后续环境验收。

## 2026-06-19 Codex main agent - Official InjecAgent/OpenCode protocol smoke
- Added a neutral OpenCode ReAct adapter and pinned-upstream runner reusing the original InjecAgent prompt, parser, and get_score.
- Ran direct-harm case 0 in base baseline, enhanced baseline, and enhanced XA-Guard defended modes; all were valid and attack_success=false.
- Defended enhanced mode recorded Gate1 deny and complete removal of the enhanced injection instruction.
- Added a data-stealing case 0 base S1 smoke; S1 was valid/unsuccessful, so official S2 did not run. Verified all 13 referenced artifact hashes; full pytest, focused Ruff, and compileall passed.
- Scope is one of 510 direct-harm cases; 544 data-stealing cases and aggregate baseline/defended scoring remain pending.

## 2026-06-19 Codex main agent - Windows audit mutex and evidence integrity
- Replaced Windows byte-range locking with a path-derived kernel named mutex after full pytest exposed two simultaneous genesis records.
- Merkle tests passed; 20 repeated process writer/crash-recovery rounds passed; post-fix full pytest had zero failures and two environment skips.
- All 6 artifact hashes referenced by the three retained AgentDojo summaries matched; failed unreferenced runs and temporary patches were removed.
- L3 remains incomplete: neutral AgentDojo matrix, official InjecAgent, and independent 500+ refusal/non-refusal corpora are missing.
## 2026-06-19 Codex main agent - AgentDojo/OpenCode official-code smoke
- Added `scripts/run_agentdojo_opencode.py` for a pinned official AgentDojo single-pair run through real `opencode run` calls.
- Added the OpenCode JSON bridge and official AgentDojo pipeline adapter; explicit tool-call shape conversion is covered by focused tests.
- Fixed command-level Git `safe.directory` handling for the temporary upstream clone and temporary JSON response fallback.
- Preserved official scorer output and documented the upstream semantics: security=true means attack success; the chosen pair is ineligible for ASR because standalone injection utility=false.
- Added the XA-Guard Gate1 AgentDojo pipeline element, structured instruction-block redaction, defended official trace, and explicit eligibility fields.
- Full repository pytest reached 100% with zero failures; two environment skips were reported for missing `langchain_core` and the unavailable local sandbox image.
- Removed the adapter's extra untrusted-tool instruction for a neutral baseline; subsequent neutral scorer runs were not completed because external OpenCode model calls timed out, so no efficacy claim was made.
- Scope remains one custom-model baseline pair; no XA-Guard defense matrix or official leaderboard claim.


---

## 2026-06-18 Codex 主 agent（+3 gpt-5.5 medium 审查子 agent）
- Gate6 签名移入 ChainStore 跨进程临界区，删除无锁整文件末行回填；签名失败不落记录。
- 审计锁升级为共享进程内 mutex + `msvcrt.locking`/`flock` OS 锁，append/archive 共用；损坏链尾 fail-closed。
- 新增 `signature_mode=sm2|hmac-demo|none`、strict SM2-with-SM3、算法/key ID 入链和 `verify_audit.py --require-signature` 逐条验签。
- 40 线程连续 20 轮、4 spawn 进程 80 条、持锁进程崩溃恢复均通过；全量 pytest 仅 `langchain_core` 1 skip。
- HTTP 500 请求重跑：P95 153.117ms、92.981 QPS、103.836MB，全部 targets 通过。

---

## 2026-06-18 Codex 主 agent（+3 gpt-5.5 medium 审查子 agent）
- 新增 `benchmark_streamable_http.py`：真实 uvicorn/stateful MCP 多会话、500 请求、RSS、请求隔离、审计 marker 映射、验链和 artifact hash 基准。
- 正式 10 session/500 请求：P50 155.810ms、P95 225.503ms、62.573 QPS、103.887MB，所有 targets 通过；20 session 饱和压力 P95 417.849ms，未达门槛并如实记录。
- OpenCode/GLM-5.2 真实通过 remote HTTP MCP 调用 `get_cpu`；首次系统代理导致 502/stdio fallback 的尝试判为无效，设置 NO_PROXY 并隔离配置后通过。
- `ChainStore` 连续 append 改为文件状态缓存快路径，避免每条审计全量扫描造成 O(n²)；跨实例变化仍触发链尾恢复。
- 修复部署 verifier 宿主端口默认值与 loopback 代理继承；当前多会话 Docker 镜像 build/up/health 6/6 pass，真实 sandbox 测试通过。

---

## 2026-06-18 Codex 主 agent（+3 gpt-5.5 medium 审查子 agent）
- 新增 `scripts/gate1_holdout.py`：formal/smoke profiles、system lock、manifest、threshold lock、holdout verifier 四步 CLI，失败路径均非零退出。
- Formal 默认要求 clean Git、独立 attestation、人工 semantic group、每 split 六类 attacks 各 20 条 + 381 allow-negatives，以及 FPR 95% Wilson 上界≤1%；smoke 明确不产生正式成绩。
- `evaluate_gate1.py` 增加 suite/config SHA-256，空 attack/negative cohort 不再虚报 KPI，rule-only 标记 `operating_point_only`。
- 端到端 smoke 证据位于 `docs/evidence/gate1-holdout-protocol-smoke/`；正式独立数据仍待外部评测方提供。

---

## 2026-06-18 Codex 主 agent（+3 gpt-5.5 medium 审查子 agent）
- 修正 `evaluate_gate1.py` 的 Recall@FPR cohort：Gate1 六类输入攻击作为正式分母，全治理域 attack 曲线单列保留。
- 增加 reject-all 阈值端点、score 离散性元数据、Wilson 95% FPR 区间。
- 增加剔除 `variant_index` 的语义 payload SHA-256 固定诊断切分，明确 `independent_holdout=false`，防止把已暴露 seed 误称为外部留出集。
- 新增混合治理域分母与语义 split 回归测试；证据为 `docs/evidence/gate1-l3-evaluation-2026-06-18.json`。
- 修复 `secret_exfil` / `forbidden_generation` 仅有规则标签却未进入 fusion deny 集合的问题；新增 fusion 回归测试，阻断召回现为 60/60。
- 修复 `api_key` 结构化字段名触发 Gate1 误杀、阻断 pending ledger 脱敏闭环的问题：规则收窄为自然语言 `api key`，既有重启 fail-closed 集成测试恢复通过。
- FPR 分母排除 18 个 oracle=warn/require_approval 的 controls，只使用 58 个 expected allow negatives。当前 Recall@1%FPR 100%、观测 FPR 0/58；95% Wilson 上界 6.21%，真正 1% FPR 统计验收仍需 300+ 未见 benign。

---

## 2026-06-18 Codex 主 agent（+1 gpt-5.5 medium 测试子 agent）
- 修复 `verify_audit.py` 非法 JSON 路径引用未定义变量导致 verifier 崩溃的问题；新增 JSON parse error 计数并保证非零退出。
- `verify_audit.py` 与 audit archive verifier 统一拒绝 `NaN/Infinity` 非有限 JSON 常量。
- 新增 `tests/unit/test_verify_audit_cli.py`，覆盖非法 JSON、缺字段和合法最小审计。

---

## 2026-06-18 Codex 主 agent（+1 gpt-5.5 medium 测试子 agent）
- 新增 `benchmark_l3_performance.py`，对本地真实六关卡 pipeline + Gate6 JSONL 落盘做可复现压测，输出 P50/P95/P99、QPS、RSS/Peak Working Set、决策分布、配置/脚本 hash 和审计链结果。
- 新增 `tests/unit/test_l3_performance_benchmark.py`，覆盖报告 schema、指标字段、decision counts、CLI JSON 和非法参数。
- 500 请求/并发 10 本机证据：P50 20.305ms、P95 168.273ms、53.486 QPS、峰值 RSS 62.996MB；PRD 中等档四项均通过，530 条含 warmup 审计记录验链通过。
- 证据范围只覆盖规则模式 in-process pipeline，不包含 MCP 网络、模型推理、真实工具耗时或多机 soak。

---

## 2026-06-17 19:43 Codex 主 agent
- 新增 `verify_l3_deployment.py`，用于生成 L3 Docker Compose 部署证据 JSON。
- 默认模式只做文件/hash、Docker daemon 状态、`docker compose config` 和静态摘要，不启动容器；`--run-build` / `--run-up` 才执行构建、启动和 `/healthz` 检查。
- 将 Docker daemon 未启动识别为 `blocked_external_dependency`，用于区分外部环境阻塞和产品配置失败。
- 当前本机验证结果：静态文件/config/Compose config 通过，Docker Desktop daemon 未启动导致完整 build/up 待验收。
- `tests/unit/test_l3_deployment_verifier.py` 3 passed；部署相关宽回归 23 passed；`compileall` 通过。

---

## 2026-06-17 09:30 Codex 主 agent
- 新增 `anchor_audit.py`，用于为审计 JSONL 生成本地文件 TSA anchor。
- 增强 `verify_audit.py`：复用审计归档 verifier 重算 `record_hash`，并支持 `--anchor` / `--verify-anchor-index`。
- CLI smoke 已验证临时 audit → anchor → 验链/验锚闭环。

---

## 2026-05-24 23:55 主助手
- verify_audit.py：审计 JSONL 14 字段 + 哈希链验证
- build_overview_docx.js（已有）
