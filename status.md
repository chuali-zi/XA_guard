# 仓库状态 · XA-Guard / XA-202620

## ⚠️ Gate2/3/4 策略评估（2026-06-04 · Claude 主 agent）

**结论：别急着横向扩规则。** 广度已偏充足（Gate3 30 条规则 / Gate2 ~50 工具 / Gate4 三色污点 + 大量敏感正则）。瓶颈不在"差哪条法条"，而在纵向工程地基没夯实——现在扩规则只会放大已有结构性问题。

### 一档：扩展前必须先修的地基裂缝
1. **risk_level 没有单一事实源**（最重要）：同一工具的风险等级在 `gate2_tool_risks.yaml` 和 `gate4_capabilities.yaml` 各手写一遍，扩到 100+ 工具必然漂移、决策自相矛盾。应让 risk_level 只有一个出处（建议归到 capabilities 总账，Gate2 派生）。
2. **fail-open 默认值方向反了**：Gate2 未登记工具默认 `GREEN`（直接放行）；Gate4 `_default_cap` 收任何脏数据（input_max=CONFIDENTIAL）、输出当公开（output=PUBLIC）。未登记新工具会同时绕过 HITL 和污点拦截。安全网关应 fail-closed。
3. **Gate4 OUTBOUND 死代码**：`gate4_taint.py:244-251` 三元两分支都是 DENY、`out_decision==WARN` 永不可达——strict_mode 是半成品，扩之前要么删要么定义清楚。

### 二档：扩展脚手架
4. **没有覆盖率矩阵**：缺"工具 × Gate 覆盖"校验，现靠肉眼比对三份 YAML。扩展前应有脚本跑出矩阵，变"填空"而非"凭感觉加"。
5. **规则无逐条正/反例绑定**：Gate3 全靠手写字符串 DSL + 硬编码中文关键词（易绕过、与 Gate1 重叠）。扩规则前先立"一规则一对测试样例"约定。

### 三档：真要扩往哪扩
- Gate2/Gate3 边界分清：red→审批在两层重复（Gate2 `risk==red` 与 Gate3 `TC260-003-9.4`）。Gate2=风险等级粗粒度 HITL，Gate3=参数/上下文细粒度合规。
- Gate4 污点分级：三色→区分"个人信息/重要数据/核心数据(国家秘密)"，比再加关键词更有纵深价值。
- `prefer_layered` 默认 False：生产推荐路径（layered）与测试默认路径（legacy 单文件）不一致，"测的不是上线跑的"。

### 建议行动顺序
`1.修 fail-open → 2.risk_level 单一源 → 3.清 Gate4 死代码 → 4.覆盖矩阵脚本 → 5.立测试样例约定 →（到这才横向扩 / 纵向加污点分级）`

一句话：**缺的不是规则数量，是让规则"可信、不漂移、可回归"的工程底座。先还债再扩才稳。**

---

更新时间：2026-06-04 23:20:17 +08:00（Codex 主 agent 补二档扩展脚手架：规则样例约定 + 工具覆盖矩阵）
维护者：Codex 主 agent / 子 agent 协助只读调查

## 最新状态快照（二档扩展脚手架）

本轮针对顶部“二档：扩展脚手架”做了两类补强。第一，新增 `docs/规则测试样例约定.md`，把 Gate3 扩规则前的“一规则一对正/反例”写成维护约定，并明确 bench case 的 `policy_refs`、`expected_decision`、`case_kind`、`source_documents` 口径。该文档同时补充了用户要求的**阳历测试样例约定**：日期默认公历/阳历，使用 ISO 8601（`YYYY-MM-DD` 或 `YYYY-MM-DDTHH:MM:SS+08:00`），默认北京时间 `Asia/Shanghai`，不得把“今天/明天/春节前/农历正月/六个月后”等相对或农历表达作为 oracle；需要相对时间语义时必须显式提供 `reference_date`。

第二，新增 `scripts/generate_tool_gate_coverage_matrix.py` 和 `tests/test_tool_gate_coverage_matrix.py`，生成独立于 `validate_csab_gov_mini.py` 的“工具 × Gate 覆盖矩阵”。矩阵读取 Gate2 `gate2_tool_risks.yaml`、Gate3 `gate3_rules.yaml`、Gate4 `gate4_capabilities.yaml` 和 bench `csab-gov-mini-seed.yaml` 四源工具名并集，输出 `bench/.log/tool_gate_coverage.md`，并在 `--strict` 下阻断 Gate3 trigger 缺 Gate2/Gate4 登记、Gate2/Gate4 risk 漂移、非法 risk/taint。`docs/XA-Bench-对抗测试规则.md` 已补覆盖矩阵口径；`docs/HACK-BENCH-组员提交规范.md` 已补日期与规则样例提交侧要求；`docs/README.md` 已把新文档纳入目录。

本轮矩阵结果：`total_tools=47`、`gate2_tools=46`、`gate3_trigger_tools=43`、`gate4_tools=46`、`bench_tools=24`。当前 **Gate3 trigger 对 Gate2/Gate4 登记无缺口**，同名工具 **Gate2/Gate4 risk_level 无不一致**，risk/taint 枚举无非法值。矩阵同时客观暴露两个仍未完成的覆盖缺口：`install_plugin` 是 25 条 supply-chain bench case 使用的 **BENCH_ONLY** 工具，尚未登记到 Gate2/Gate3/Gate4；另有 23 个 Gate3 trigger 当前没有 bench case 覆盖，包括 `admin_action`、`append_file`、`call_model`、`train_model`、`shell` 等。

验证结果：
- `python scripts\generate_tool_gate_coverage_matrix.py --strict`：通过，生成 `bench\.log\tool_gate_coverage.md`；当前输出 `missing_gate2=0`、`missing_gate4=0`、`risk_mismatches=0`、`bench_only=1`、`gate3_no_bench=23`。
- `python scripts\validate_csab_gov_mini.py --strict`：通过，290 条 case errors=0/warnings=0，并刷新 `bench\.log\coverage.md`。
- `python -m pytest -q --basetemp pytest_tmp_rule_matrix -p no:cacheprovider tests\test_tool_gate_coverage_matrix.py tests\test_csab_gov_mini_assets.py`：通过，10 个测试点。
- `python -m pytest -q --basetemp pytest_tmp_gate3_rules -p no:cacheprovider tests\unit\test_gate3.py -x --tb=short`：通过，46 个 Gate3 测试点。

客观限制：
- “一规则一对正/反例”目前已文档化，但还没有独立的 `gate3-rule-fixtures.yaml` / schema / validator 来强制每条规则都有正例和反例；现有 `tests/unit/test_gate3.py` 仍是前 10 条较完整、后续扩展规则抽样覆盖。
- 覆盖矩阵当前是 baseline + bench 视图，尚未纳入 `policies/overlay/<tenant_id>/` 的真实租户 overlay 合并视图。
- `BENCH_ONLY` 和 `NO_BENCH_CASE` 目前作为显式缺口报告，不在 `--strict` 中阻断；如果后续把 `install_plugin` 纳入统一工具总账，或要求每个 Gate3 trigger 必须有 bench case，可再升级为 strict。

---

更新时间：2026-06-04 22:23:39 +08:00（Codex 主 agent 安装本地 OPA 并补真实 eval 测试）
维护者：Codex 主 agent / Claude 主 agent

## 最新状态快照（OPA 本地二进制与真实 eval）

本轮已按用户要求把 OPA Windows amd64 二进制下载到仓库内 `tools/opa/opa.exe`，版本为 **OPA 1.17.0 / Rego v1 / windows/amd64**，本地 SHA256 为 `D319E1ABCA6B1683E79E4E3DDB840B098C45A9257426BA998917DAC8D83B7574`。该二进制来自 OPA 官方 latest 下载入口，文件较大且属于本地工具，因此已加入 `.gitignore`，不作为源码资产提交。

Gate3 Rego 后端进一步补齐：`RegoPolicyEngine` 现在查找顺序为显式 `opa_path` → PATH 中的 `opa` → 仓库本地 `tools/opa/opa.exe`。真实 OPA CLI 测试已补入 `tests/unit/test_gate3.py`，覆盖显式路径和默认本地发现两条路径；测试中使用 `strict_opa=true`，因此实际执行的是 `opa eval`，不是 Python fallback。

本轮修复了一个真实 OPA smoke 暴露的问题：OPA 1.17.0 在本机对 Python 临时目录的 Windows 绝对路径处理失败，报找不到 `\Users\...\gate3.rego`。当前 `_evaluate_opa()` 改为在临时目录内以 `cwd=tmpdir` 调用 OPA，并把 `--data gate3.rego --input input.json` 作为相对路径传入，真实 OPA smoke 已通过。

验证结果：
- `tools\opa\opa.exe version`：OPA 1.17.0，Rego Version v1，Platform windows/amd64。
- `python -m pytest -q --basetemp pytest_tmp_opa_real -p no:cacheprovider tests\unit\test_gate3.py::test_rego_backend_evaluates_with_real_local_opa tests\unit\test_gate3.py::test_rego_backend_discovers_local_opa_by_default -x --tb=short`：通过，2 条真实 OPA CLI smoke。
- `python -m pytest -q --basetemp pytest_tmp_opa_gate3 -p no:cacheprovider tests\unit\test_gate3.py -x --tb=short`：通过，46 个 Gate3 测试点。
- `python -m pytest -q --basetemp pytest_tmp_opa_related -p no:cacheprovider tests\unit\test_gate2.py tests\unit\test_gate3.py tests\unit\test_gate4.py tests\unit\test_layered_policy.py -x --tb=short`：通过。
- `python -m pytest -q --basetemp pytest_tmp_opa_full -p no:cacheprovider -x --tb=short`：通过；`tests\integration\test_sandbox_runner.py` 仍因当前 shell 未发现 Docker 被 skip。

剩余限制：
- `tools/opa/opa.exe` 是本地下载工具，已被 `.gitignore` 忽略；新机器需要重新下载或把 OPA 放进 PATH，真实 OPA smoke 才会执行，否则测试会 skip。
- `prefer_layered=true` 的 `LayeredPolicySource` 合并视图仍未统一切到 Rego engine；当前真实 OPA 测试覆盖 Gate3 legacy policy_file 路径。
- 还没有把 OPA bundle 导出、OPA 版本约束、策略失败 fail-closed 产品策略纳入配置。

更新时间：2026-06-04 22:09:48 +08:00（Codex 主 agent 落地 Gate3 OPA/Rego 后端 MVP）
维护者：Codex 主 agent / Claude 主 agent

## 最新状态快照（Gate3 OPA/Rego）

本轮把 `gate3_policy.py` 的 `backend=rego` 从 `NotImplementedError` 占位推进为可运行 MVP。新增 `src/xa_guard/policy/rego.py`：将现有 PolicyRule predicate DSL 通过 Python AST 转译为 Rego module 文本，同时提供 `RegoPolicyEngine`。运行时若能找到或配置 `opa_path`，会通过 `opa eval` 评估 `data.xa_guard.gate3.hit`；若当前环境没有 OPA 且未开启 `strict_opa`，则使用与现有 Python predicate 相同语义的 fallback，metadata 会写明 `rego_mode=python_fallback`、`opa_available=false`。若 `strict_opa=true` 且没有可用 OPA binary，会 fail-fast 抛错，避免生产误以为走了真实 OPA。

本轮已补 `tests/unit/test_gate3.py`：覆盖 Rego backend fallback 命中、`strict_opa` 缺 binary 抛错、现有 30 条 DSL predicate 可转译成 Rego module。Gate3 现在可用 `options={"backend": "rego", "policy_file": ...}` 实例化和评估，不再是空壳。

验证结果：
- `python -m pytest -q --basetemp pytest_tmp_rego -p no:cacheprovider tests\unit\test_gate3.py -x --tb=short`：通过。
- `python -m pytest -q --basetemp pytest_tmp_rego_related -p no:cacheprovider tests\unit\test_gate2.py tests\unit\test_gate3.py tests\unit\test_gate4.py tests\unit\test_layered_policy.py -x --tb=short`：通过。
- `python -m pytest -q --basetemp pytest_tmp_rego_full -p no:cacheprovider -x --tb=short`：通过；`tests\integration\test_sandbox_runner.py` 仍因当前 shell 未发现 Docker 被 skip。

客观限制：
- 2026-06-04 22:23 更新：本机已下载 `tools/opa/opa.exe` 并补真实 `opa eval` smoke；此前“未实测真实 OPA CLI”的限制已解除到 Gate3 legacy policy_file 路径层面。
- `prefer_layered=true` 的全局 `LayeredPolicySource` 仍返回 Python compiled predicates，尚未把 overlay/hot-reload 的合并视图切到 Rego engine。
- Rego 转译器覆盖了当前 `policies/enterprise-l3.yaml` 的 predicate 形态；如果后续 DSL 引入复杂 Python 表达式，需要先扩展 AST 白名单和转译测试。

更新时间：2026-06-04 21:55:12 +08:00（Codex 主 agent 侦察 Gate2/Gate3/Gate4 完成度）
维护者：Codex 主 agent / Claude 主 agent

## 最新状态快照（Gate2/Gate3/Gate4）

本轮只读侦察确认：Gate2/Gate3/Gate4 这一串当前不是空壳，已经达到 **规则链路 demo / M2 雏形** 水平。可运行主链路是 `gate2_plan` 先做工具风险分级与 HITL 触发，`gate4_taint` 做入向污点与工具能力边界，`gate3_policy` 再用国标/企业规则 predicate 聚合最终执行前决策；pipeline 顺序仍是 Gate1 → Gate2 → Gate4(in) → Gate3 → Gate5 → executor → Gate4(out) → Gate6，且 Gate3 的 DENY 可以覆盖 Gate2 的 REQUIRE_APPROVAL。

当前 baseline 规模经本轮脚本核对为：`policies/enterprise-l3.yaml` 30 条规则、43 个唯一 Gate3 trigger；`policies/tool_risks.yaml` 46 个工具风险；`policies/tool_capabilities.yaml` 46 个工具能力；`policies/sensitive_patterns.yaml` 29 条敏感模式。Gate3 43 个 trigger 当前全部能在 Gate2 risk 与 Gate4 capability 中找到登记；同名工具在 Gate2/Gate4 的 `risk_level` 未发现不一致。`policies/overlay/` 目前只有 `_template`，没有真实租户 overlay，因此生产配置虽已开启 `prefer_layered: true`，实际主要还是 baseline 生效。

本轮验证结果：
- `python -m pytest -q -p no:cacheprovider --basetemp pytest_tmp_gate234_scout tests\unit\test_gate2.py tests\unit\test_gate3.py tests\unit\test_gate4.py tests\unit\test_layered_policy.py -x --tb=short`：通过；收集口径为 14 + 42 + 22 + 33 = 111 个测试点。
- `python scripts\enrich_csab_gov_mini.py --check`：通过，290 条 bench YAML 元数据为最新。
- 策略统计脚本：rules=30、tool_risks=46、tool_capabilities=46、sensitive_patterns=29、unique_triggers=43、trigger_missing_risk=[]、trigger_missing_capability=[]、risk_cap_level_mismatch=[]。

客观完成度估计：Gate2 约 **80%**，Gate3 约 **70%**，Gate4 约 **75%**，三者串联整体约 **75%**。已经完成的是 baseline 策略资产、双层加载框架、单调性门控、热加载入口、审计 bundle_sha 字段、关键错位修复和单元测试守护；还没完成的是真实租户 overlay 使用场景、overlay merge 阶段的跨资源一致性强校验、统一工具目录/自动生成、OPA/Rego 后端、`bundle_sha` 只表示“当前生效快照”的严格语义、真实客户端 HITL UI 证据以及真实 MCP/模型评测并入 bench 指标。

## 最新状态快照（Gate5）

本轮后，Gate5 已从“只输出 sandbox routing metadata”推进到“可执行 Docker/gVisor sandbox 接入点”。当前 `Gate5Sandbox` 仍负责按风险等级路由：green → `native`，yellow → `docker`，red → `docker_gvisor`（若未配置 `runsc` 则降级 `docker`）；但它现在会输出 executor 可消费的结构化策略字段，包括 `sandbox_enforced`、`network_disabled`、`readonly_rootfs`、`memory`、`cpus`、`pids_limit`、workspace mount 策略、`docker_image` 和 `runtime`。

`DownstreamRouter.call_tool()` 已开始消费 Gate5 策略：`native` 继续走既有常驻 MCP downstream session；`docker` / `docker_gvisor` 会按 `src/xa_guard/sandbox.py` 构造 `docker run`，通过临时 stdio MCP server 调用下游工具，调用结束后关闭。Docker 命令当前包含禁网、只读 rootfs、drop capabilities、no-new-privileges、进程/内存/CPU 限制、只读挂载 workspace；`docker_gvisor` 模式会加 `--runtime runsc`。Gate6 审计新增 `gen_ai.tool.sandbox.mode/enforced/image/runtime`，能记录本次调用实际采用的 sandbox 策略。

2026-06-04 更新：本机已安装 Docker Desktop（client/server 29.5.2）并跑通**真实 Docker smoke**。仓库新增 `docker/sandbox.Dockerfile`（非 root uid 10001 的 `python:3.12-slim`）+ `scripts/build_sandbox_image.sh`，`xa-guard/sandbox:latest` 现可复现构建；`tests/integration/test_sandbox_runner.py` 不再被 skip，真实容器内探针实测 `network=OSError`（`--network none` 阻断外联 1.1.1.1:80）、`root_write=OSError`（`--read-only` 阻止写根 FS），印证 `build_docker_command` 下发的禁网 / 只读 rootfs / `--cap-drop ALL` / `no-new-privileges` / pids/内存/CPU 限制全部生效。默认 demo 配置和 `XAGuardConfig()` 仍保持 Gate5 Docker disabled，避免无 Docker 环境误触发；显式开启 Gate5 后才会进入真实 Docker/gVisor 路径。仍未在本机验证的是 gVisor(`runsc`) runtime（Docker Desktop/Windows 无 runsc）。

最新验证：
- `PYTHONPATH=src python -m pytest tests/integration/test_sandbox_runner.py -v`（PATH 注入 Docker Desktop 的 `docker.exe` 后）：**1 passed**，真实容器证明禁网与只读 rootfs 生效。
- `python scripts/enrich_csab_gov_mini.py --check`：通过。
- `PYTHONPATH=src python -m bench.cli run --suite bench\cases\csab-gov-mini-seed.yaml --config configs\xa-guard.yaml`：290 条通过，pass_rate 1.0，ASR 0.0，FPR 0.0，Recall 1.0，P50/P95 54.25/85.59 ms。
- `PYTHONPATH=src python scripts\verify_audit.py --path logs\audit\audit.jsonl`：15526 条记录，0 chain errors，0 missing-field records。

Gate5 距离 PRD 目标的剩余差距：
- ~~需要补 Dockerfile / 镜像构建脚本，保证 `xa-guard/sandbox:latest` 可复现构建。~~ — 2026-06-04 完成（`docker/sandbox.Dockerfile` + `scripts/build_sandbox_image.sh`）。
- 真实 Docker smoke 已在本机（Docker Desktop/Windows）跑通，禁网 + 只读 rootfs 实测生效；仍需在 Linux + runsc(gVisor) 环境验证 gVisor runtime，并把沙箱接入真实 MCP E2E。
- 需要决定 Docker 不可用、镜像缺失、runsc 缺失时的产品策略：fail-closed、降级 Docker、回退 approval，还是只审计警告；当前只有 red runtime 非 runsc 的路由降级，Docker 缺失会在显式启用路径中表现为执行失败。
- 当前仅支持 stdio downstream 的沙箱化；streamable-http downstream 仍未实现。
- 当前是 Docker/gVisor MVP，不是 Codex 那类 OS-native Landlock/seccomp/Seatbelt/Windows restricted-token 抽象。

更新时间：2026-06-04 +08:00（Claude 主 agent 跑通 Gate5 真实 Docker smoke、镜像构建文件入库、刷新 Gate5 状态）
维护者：Codex 主 agent / Claude 主 agent

## 总体判断

当前仓库仍应定位为 **demo MVP / M1 末到 M2 前的可运行骨架**，不是 PRD 目标里的 L3 政企原型。主线已经成立：双面 MCP 代理把 LLM 客户端和下游工具隔开，中间串 6 个安全关卡，并用 XA-Bench、审计 JSONL 和前端时间线提供演示证据。

2026-06-02 本轮补齐前次侦察确认的 Gate2/3/4 baseline 明显错位：`post_url` 现在在 Gate2 和 Gate4 均为 yellow 外联工具；`delete_file`、`drop_table` 在 Gate4 有显式 red capability；`shell`、`append_file`、`content_generation`、`red_operation` 的 Gate3 trigger/predicate 与 Gate2 风险登记已对齐。当前更准确的状态是：**共享加载源已完成，本轮选定错位已补齐；跨资源一致性自动校验、统一工具目录和 bundle_sha 生效语义仍未完成**。

本轮仍保留的后续项：
- overlay 单调性已有单资源校验，但缺少跨资源一致性校验，例如同一工具在 `tool_risks.yaml` 与 `tool_capabilities.yaml` 的 `risk_level` 是否一致。
- Gate3 的 30 条规则仍覆盖大量政企/模型/训练/审计工具，未对所有 trigger 建立“必须登记 Gate2/Gate4 或显式豁免”的自动检查。
- `bundle_sha` 当前会纳入被拒绝 overlay 的文件字节，和“当前生效策略快照”的审计语义存在偏差。

本轮更新的关键纠偏是：**当前工作区可复现的 bench 是规则链路 + mock executor 口径，不是 Qwen3Guard 真实模型推理口径**。`configs/xa-guard.yaml` 虽然配置了 `model_qwen` 且 `dry_run: false`，但当前环境没有项目 `.venv`，全局 Python 也未安装 `transformers` / `torch` / `huggingface_hub`；模型 detector 当前 `is_ready=False` 并 fail-open，bench 延迟不能宣传成真实模型延迟。

本轮已按用户要求完成两项规模化补强：**Policy DSL 从 10 条扩到 30 条**，`bench/cases/csab-gov-mini-seed.yaml` 从 30 条扩到 **290 条**。规则和样例围绕等保 2.0 / GB/T 22239-2019、GB/T 45654-2025、TC260-003 补充了日志留存、备份与加密、关键岗位权限、CII/重要场景、训练数据授权、robots 禁采、商业来源证明、个人/敏感个人信息、第三方模型备案、模型更新安全评估、标注职责隔离、未成年人保护、AI 生成合成内容标识、连续诱导违法输入处置等主题。事实源采用官方页面复核：GB/T 22239-2019 为 2019-05-10 发布、2019-12-01 实施的现行标准；GB/T 45654-2025 为 2025-04-25 发布、2025-11-01 实施的现行推荐性国标；TC260-003 为 TC260 于 2024-03-01 发布的技术文件。

2026-06-02 进一步把 290 条升级为「可信评测资产」：每条 case 现在带 `case_kind`（attack_case 193 / benign_control 76 / assurance_check 21）、`source_documents`（按 policy_refs 前缀映射到 GB/T 22239-2019、GB/T 45654-2025、TC260-003、网安法、AIGC 标识办法；合计 137 / 148 / 48 / 12 / 11 条引用）、稳定 `fingerprint`；fingerprint 全部唯一（重复 payload 通过 `variant_index` 解碰撞）。新增 `bench/schema/csab-gov-mini.schema.json` + `scripts/enrich_csab_gov_mini.py`（幂等，`--check` 给 CI）+ `scripts/validate_csab_gov_mini.py`（必填字段 / ID 唯一 / fingerprint 唯一 / policy_refs 白名单 / metadata 对账，`--strict` 把告警提为错误）+ `tests/test_csab_gov_mini_assets.py` 7 个用例钉在 CI 里，避免 YAML 继续扩量后悄悄回退。当前 `validate --strict` errors=0/warnings=0，`pytest` 183 passed，bench 290/100%。

2026-06-02 三次刷新落地 **Gate2/3/4 双层策略层**（对标 Google Model Armor Floor Settings + AWS SCP Deny-不被-IAM-Allow-推翻 + Kubernetes Gatekeeper ConstraintTemplate）。新增 `src/xa_guard/policy/{layered,monotonicity,predicate_safe,hot_reload}.py` 四个模块和 `policies/baseline_manifest.yaml` + `policies/sensitive_patterns.yaml` + `policies/overlay/_template/`。`LayeredPolicySource` 把 baseline（项目内置国标兜底，运行时只读）和 overlay（`policies/overlay/<tenant_id>/*.yaml`，企业可写）合并为单一视图给三家 Gate 共享；单调性门控强制 4 类红线（rule.id 不可覆盖、tool_risks 不可弱化、`input_max_taint` 不可放宽、敏感词不可删 baseline）违例则整批 overlay 拒绝加载并保留旧 snapshot。overlay predicate 走 AST 白名单（`evalidate` 优先，缺失时内置 walker）。`watchfiles` 监听 overlay 目录做原子热加载。每次合并出 `bundle_sha`（baseline + overlay 文件字节 sha256），通过 `gen_ai.policy.bundle_sha` 字段贴入每条 `AuditRecord`，让监管可复现"事故时哪个版本生效"。Gate2/3/4 增加 `prefer_layered` 开关（生产 true / 单测 false）。本轮进一步补齐后 baseline 当前为 30 条策略规则 + 46 个工具风险 + 46 个工具能力 + 29 条敏感模式；Gate3 当前 43 个唯一 trigger 均已在 Gate2/Gate4 登记，Gate2/Gate4 同工具 `risk_level` 已由自动测试钉住；`call_model` 被视为外部模型调用边界，内部跨域外发从 warn 升级为 require_approval。`pyproject` 把 `evalidate` + `watchfiles` 放进新的 `[policy]` extra（可选依赖，缺失时自动降级到内置兜底）。

## 与赛题 4 个方向的贴合度

| 赛题方向 | 当前仓库状态 | 空位 / 未完成 |
|---|---|---|
| 方向 1：复杂输入链路攻击识别 | `gate1_input.py` 已有规则检测、模型 detector 壳子、fusion、Qwen3Guard / PromptGuard / ShieldLM / LlamaGuard 后端代码；当前配置启用 Qwen3Guard 后端但本机缺模型依赖，实际可复现为规则层 fail-open 链路。 | 当前 `spotlighting.enabled: false`，不是默认开启；没有 Recall@1%FPR、adaptive attack、AgentDojo/InjecAgent 指标；当前环境未复现真实 Qwen 推理；PromptGuard2 / Llama Guard 仍受 gated 授权限制，ShieldLM-14B 资源过大。 |
| 方向 2：工具调用与任务执行安全 | `gate2` 风险分级、`gate3` Python 策略与 Rego backend MVP、`gate4` 三色污点、`gate5` 沙箱路由决策已存在；pipeline 已能让 Gate3 DENY 覆盖 Gate2 REQUIRE_APPROVAL；Policy DSL 已扩到 30 条并覆盖等保/生成式 AI 治理主题；上游有最小 MCP elicitation approve/reject 逻辑和 toy probe。**Gate2/3/4 已落地 baseline+overlay 双层策略：项目自带 30 条规则 + 46 工具风险 + 46 工具能力 + 29 敏感模式为 baseline；企业可在 `policies/overlay/<tenant_id>/` 注入私有规则，单调性门控强制不得弱化国标，热加载经 watchfiles 落地，`bundle_sha` 进 audit。** | **真实 JSON-RPC `tools/call` + elicitation approve/reject + 下游调用计数 + 审计一致性已由 `test_mcp_e2e.py` E2E harness 端到端覆盖（进程内内存 transport）。** 真实 Cursor / Claude Code / Codex 弹窗 UI 未人工实测；国产客户端仍只能写 fallback；OPA/Rego 已有 Gate3 backend MVP，但当前环境未实测真实 OPA CLI，layered/hot-reload 合并视图仍走 Python predicate；Docker/gVisor 只给路由决策不执行真实沙箱；**approval_token / approver / reason / expiry / args_hash 已进入审计闭环（`src/xa_guard/approval.py` HMAC 签发验签，`run_after_approval` 执行前验签做执行闸门）。** 统一工具目录仍未实现，当前靠测试保证 baseline 对齐。 |
| 方向 3：插件 / Skill / 脚本供应链安全 | `src/xa_guard/aibom/` 已有本地静态扫描、依赖风险解析、A/B/C/D/F 评级、CycloneDX-like 导出、本地 artifact/file URL/zip/tar 解包、sha256 provenance、typosquat 启发式和 drift 比较；4 条 supply_chain seed 通过。 | 没有远程包下载、外部信誉库、漏洞库、真实签名体系、Sigstore/TUF、公钥校验、CycloneDX schema 校验；bench 的 supply_chain case 仍走简化评级路径，不覆盖完整 artifact + provenance + audit。 |
| 方向 4：评测与审计溯源 | `Gate6Audit`、哈希链、OTel 字段、`bench` CLI、HTML report、前端时间线已存在；CSAB-Gov-mini 已扩到 290 条并刷新报告；旧损坏审计链已归档，当前主日志验链通过；**新增 `test_mcp_e2e.py` 在真实 `tools/call` 链路上断言审计 decision 序列与逐场景验链。** | 290 条仍是规则链路 + mock executor 口径，bench 自身尚不是真实 MCP E2E / 真实模型评测（E2E harness 已独立覆盖真链路审计一致性，但未并入 bench 指标）；`audit_completeness` 固定 1.0，不是逐 case 实测；pipeline 异常仍可能被 runner 吞掉；SM3/SM2 是 fallback，CoT faithfulness 是占位。 |

## 当前可用能力

- Python 包骨架与 CLI 存在：`xa-guard` / `xa-bench` entry points 已配置。
- 6 个 gate 文件均有实现，pipeline 可串起 gate1 → gate2 → gate4(in) → gate3 → gate5 → executor → gate4(out) → gate6。
- stdio 上游 MCP server 与 stdio 下游 MCP client 已有 smoke 测试。
- Gate1 规则层可用；模型后端代码存在并 fail-open，不阻塞 pipeline。
- Gate2 可对 red/yellow/green 工具做审批/告警/放行决策。
- Gate3 可加载 `policies/enterprise-l3.yaml` 的 30 条 Python predicate 规则；`backend=rego` 已可生成 Rego module，并在有 OPA binary 时走 `opa eval`，无 OPA 时默认走可审计的 Python fallback。
- Gate4 可做三色污点与外发工具能力判断；中文敏感词扫描已补手机号、银行卡、医疗健康、金融账户、行踪轨迹、敏感个人信息。
- Gate5 可输出 `native` / `docker` / `docker_gvisor` 路由元数据并执行真实 Docker 沙箱（`xa-guard/sandbox:latest` 可由 `scripts/build_sandbox_image.sh` 构建，真实 smoke 已验证禁网 + 只读 rootfs）；默认仍禁用 Docker。
- Gate6 可写审计 JSONL；当前主审计日志哈希链可验。
- AIBOM 本地 MVP 已能支撑方向 3 的 seed 演示。
- `bench` 能跑 290 条 CSAB-Gov-mini 样例并生成 `bench/.log/last_results.json`、`last_report.json`、`report.html`。
- 前端是离线审计时间线，可作为演示素材，但不是完整管理后台。

## 主要空壳 / 占位清单

1. **SDK 是空的**：`sdk/decorators.py` 的 `@protect` 只透传原函数，没有 mini-pipeline、LangChain callback、Guard session。
2. **Gate1 当前环境不是模型实测**：当前机器无 `.venv`，全局 Python 未安装 `transformers` / `torch` / `huggingface_hub`；Qwen backend `is_ready=False`，bench 为规则链路。
3. **Spotlighting 当前默认未开启**：`configs/xa-guard.yaml` 中 `spotlighting.enabled: false`。
4. **MCP elicitation 缺真实客户端 UI 证据**：toy MCP 协议 probe 与最小 upstream 逻辑存在，但 Cursor / Claude Code / Codex 的真实弹窗点击记录未完成。
5. **Streamable HTTP 未实现**：上游 `run_streamable_http()` 直接 `NotImplementedError`；下游也只支持 stdio。（注：stdio 链路的真 JSON-RPC `tools/call` + elicitation approve/reject + 下游调用计数 + 审计一致性已由 2026-06-04 新增的 `test_mcp_e2e.py` E2E harness 覆盖。）
6. ~~**OPA / Rego 未实现**~~ — 2026-06-04 已完成 Gate3 backend MVP。`backend=rego` 不再抛 `NotImplementedError`，可生成 Rego module、可选调用 OPA CLI，并提供无 OPA 环境 fallback；剩余是真实 OPA binary 环境实测、layered/hot-reload 合并视图接入 Rego、复杂 DSL 转译扩展。
7. **Docker 真沙箱已执行，gVisor 仍未实测**：`gate5_sandbox.py` 路由 + `sandbox.build_docker_command` + `DownstreamRouter` 已能把下游调用放进真实 `docker run`（禁网 / 只读 rootfs / 降权 / 资源限制经 2026-06-04 本机真实 smoke 验证生效）；剩余空位是 gVisor(`runsc`) runtime 未在 Linux 实测、streamable-http 下游未沙箱化。
8. ~~**审批闭环不完整**~~ — 2026-06-04 完成。`src/xa_guard/approval.py` 用 HMAC-SHA256 签发/验签 approval_token，payload 绑定 `trace_id + tool_name + args_hash + approver + issued_at + expires_at`；`pipeline.run_after_approval` 执行前 `verify_approval`（缺令牌 / 改参 TOCTOU / 伪造签名 / 过期 → DENY 且下游不执行），令牌是真正的执行闸门而非审计装饰；`proxy/upstream.py` 在人工 approve 时 `issue_approval` 挂到 `ctx.approval`；Gate6 把 approval_token/approver/reason/expires_at/args_hash 写入审计。剩余：审批人身份目前取 MCP client info（非强认证）；HMAC demo 密钥，生产可换 SM2/RSA 非对称签名。
9. **国密证据链不完整**：SM3/SM2 依赖 gmssl fallback；没有 TSA；签名不是正式 SM2 私钥流程。
10. **CoT 忠实度未实做**：审计字段里有 `faithfulness_score=1.0`，但没有解释性/忠实度检测算法。
11. **bench 指标仍是 demo 口径**：ASR / Recall 由 `expected_decision != allow` 推导，会混入治理审批类；CuP 是非阻断代理指标；`audit_completeness` 固定 1.0。
12. **bench 不是 MCP E2E**：普通 case 直接构造 `GateContext` 并使用 mock executor；真实 MCP stdio、审批恢复、多步工具链仍需独立 harness。
13. **供应链 seed 是简化路径**：4 条 `install_plugin` case 走独立 AIBOM rater，不覆盖完整本地 artifact 解包、provenance、导出、drift 和 Gate6 审计。
14. **评测仍是 mini / PoC 口径**：CSAB-Gov-mini 已达到 290 条，但仍不是 GB/T 45654 完整题库规模；普通 case 仍使用 mock executor，不能替代真实 MCP E2E 和真实模型评测。
15. **Protocol PDF / 技术方案 / 演示视频未交付**：比赛必交的 30 页技术方案 PDF、10 分钟视频、报名表不在仓库内完成。

## 最新验证结果

本次维护在当前工作区重新执行（2026-06-04）：

- `PYTHONPATH=src python -m pytest -p no:cacheprovider`：通过，230 个测试点全绿（19.32s）。
- `python scripts/enrich_csab_gov_mini.py --check`：通过，290 条 bench YAML 元数据为最新。
- `PYTHONPATH=src python -m bench.cli run --suite bench/cases/csab-gov-mini-seed.yaml --config configs/xa-guard.yaml`：通过运行，刷新 `bench/.log/last_results.json` / `last_report.json` / `report.html`；290 条 pass_rate 100.0%。
- `PYTHONPATH=src python scripts/verify_audit.py --path logs/audit/audit.jsonl`：通过，12694 条记录，0 个链错误，0 条缺字段。
- `PYTHONPATH=src python -m pytest tests/integration/test_mcp_e2e.py`：通过（新增 MCP E2E harness）。
- `PYTHONPATH=src python -m pytest`：全量 **240 passed**（230 基线 + MCP E2E 1 + 审批令牌 9 例，并修订 test_upstream_elicitation / test_pipeline_smoke 适配新审批契约）。
- `PYTHONPATH=src python scripts/verify_audit.py`（bench 重跑后）：**14605 条记录，0 链错误，0 缺字段**，新增审批字段未破坏哈希链。

2026-06-04 新增 **MCP E2E harness**（`tests/integration/test_mcp_e2e.py` + `_fixture_e2e_server.py`）：用 mcp 进程内内存 transport 把真实 `ClientSession` 接到 `proxy.upstream._build_app` 构造的 guard `Server` 上，发起**真实 JSON-RPC `tools/call`**，弥补此前 `test_proxy_smoke` 绕过上游 MCP 协议层、从未走真 elicitation 的空缺。覆盖四场景并逐条断言：allow（echo，下游调用 1 次、审计 1 条 allow）、deny（exec_command rm -rf，Gate1 拦截、下游 0 次、审计 1 条 deny）、approve（grant_permission 触发 Gate2 REQUIRE_APPROVAL，客户端 elicitation 回 `approve=true` → 下游 1 次、审计 `require_approval`→`allow` 两条）、reject（elicitation `decline` → 下游 0 次、审计 1 条 require_approval）。`CountingRouter` 统计真正触达下游的次数，末尾 `ChainStore.verify()` 校验本场景 5 条审计记录哈希链完好。

2026-06-04 进一步落地 **审批令牌审计闭环**（status 第8条空壳清零）：新增 `src/xa_guard/approval.py`，用 HMAC-SHA256 对 `{trace_id, tool_name, args_hash, approver, issued_at, expires_at}` 签发 `approval_token`。关键是把令牌做成**执行闸门**而非审计装饰——`pipeline.run_after_approval` 在调用下游前 `verify_approval`，任一条件不满足（缺令牌 / 审批后篡改入参 TOCTOU / 伪造签名 / 过期）即 `DENY` 且下游绝不执行。`proxy/upstream.py` 的 `_request_hitl_approval` 改为返回 `_ApprovalOutcome(approved/approver/reason)`，在人工 approve 时 `issue_approval` 挂到 `ctx.approval`；Gate6 把 `approval_token` + 新增的 `approver/reason/expires_at/args_hash` 四字段写入 `AuditRecord`。新增 `tests/test_approval.py` 9 例覆盖验签各失败模式 + pipeline DENY/TOCTOU，E2E approve 场景加断言验证 allow 审计记录确带可验证令牌。仍存空位：下游是 fixture echo 而非生产工具；审批人身份取 MCP client info（非强认证）；HMAC demo 密钥，生产可换 SM2/RSA 非对称签名。

最新 bench 指标：

| 指标 | 最新值 | 说明 |
|---|---:|---|
| total | 290 | 已达到 CSAB-Gov-mini 290 条目标，但仍是 mini/PoC，不是国标完整题库 |
| pass_rate | 100.0% | 290 条规则链路样例 exact match |
| legacy seed ASR | 0.0% | 当前按 `expected_decision != allow` 推导攻击集合，会混入治理动作 |
| legacy seed Recall | 100.0% | 当前是 `1 - legacy seed ASR`，不能等同模型 Recall@FPR |
| FPR | 0.0% | 新口径下 WARN 不算阻断 |
| CuP proxy | 100.0% | 只是合法样例非阻断率，不验证真实任务完成 |
| Latency P50 / P95 | 29.93 ms / 34.02 ms | 当前是规则 pipeline + mock executor + 模型 fail-open；不是 Qwen 真实推理延迟 |
| audit_completeness | 占位 100% | bench 固定写 `1.0`；独立 `verify_audit.py` 对当前主日志 12694 条可验，0 链错误 |

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
5. ~~**建立 MCP E2E harness**：覆盖 stdio `tools/call`、approve/reject、下游调用次数、审计一致性。~~ — 2026-06-04 完成。`tests/integration/test_mcp_e2e.py` 用 mcp 内存 transport 走真 JSON-RPC，四场景（allow/deny/approve/reject）逐条断言下游调用次数 + 审计 decision 序列 + 验链。后续可扩展：真实 stdio 下游生产工具、多步工具链、approval_token 进审计闭环。
6. **真实客户端 HITL 弹窗实测**：在明确支持 elicitation 的客户端完成 approve/reject 点击和截图/日志；国产客户端继续按事实源写 fallback。
7. ~~**审批令牌与审计增强**：补 approval_token、approver、reason、expiry、args_hash，并进入 Gate6 审计。~~ — 2026-06-04 完成（`src/xa_guard/approval.py` + `pipeline.run_after_approval` 执行前验签 + Gate6 审计字段 + 9 个单测）。后续可做：把审批人接入强认证、HMAC 换 SM2 非对称签名、approval_token 在 verify_audit 里做跨记录一致性校验。
8. **Gate5 gVisor 与 Gate3 OPA**：Docker 真沙箱已落地并本机验证（2026-06-04）；剩余在 Linux + runsc 验证 gVisor runtime、把沙箱接入真实 MCP E2E；把 Python predicate 后端扩展到 OPA/Rego。
9. **AIBOM 生产化**：补 CycloneDX schema 校验、签名/公钥校验、远程包离线拉取、外部信誉库/漏洞库、持续漂移监测任务。
10. ~~**把 290 条 mini 样例升级为可信评测资产**~~ — 2026-06-02 完成。新增 `bench/schema/csab-gov-mini.schema.json`、`scripts/enrich_csab_gov_mini.py`（幂等，`--check` 给 CI）、`scripts/validate_csab_gov_mini.py`（必填字段 / ID & fingerprint 唯一 / policy_refs 白名单 / metadata 对账 / `--strict`）、`tests/test_csab_gov_mini_assets.py` 7 个用例；290 条全部带 `case_kind` + `source_documents` + `fingerprint`；`bench/.log/coverage.md` 输出覆盖率报告。后续若再扩量应换样本而不是堆 `variant_index`，并把 `source_documents` 的 fallback 引用对齐到附录小节级别。
