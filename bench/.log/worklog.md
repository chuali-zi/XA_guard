# bench 模块工作日志

---

## 2026-06-17 Codex 主 agent — external archive projection evidence

- `xa_guard_projection.input_payload` 现在优先从 normalized 外部记录的首个 tool call/action 中提取 tool name 和 arguments，增强本地投影价值。
- 新增 `bench.external.projection.run_projection()`：把 normalized records 送入本地 XA-Guard pipeline，使用 mock executor，生成 projection decisions，并把 Gate6 audit 写到 archive 内部隔离目录。
- `bench.external.cli archive --run-projection` 新增 `xa-guard-projection/results.json`、`summary.json`、`audit/audit.jsonl`、`audit-verify.json`；manifest 记录 projection hash、audit hash、audit verify、config hash 和非官方 claim scope。
- 单测覆盖 projection 不污染 smoke metrics、summary 不使用官方分数字段、audit 隔离与验链。

---

## 2026-06-17 Codex 主 agent — external evidence archive

- 新增 `bench.external.report.build_report()`，对 normalized external JSONL 生成非官方 report：输入 hash、schema/adapter 版本、validation errors、benchmark/task 分布、label 覆盖、smoke metrics、limitations。
- 扩展 `bench.external.cli`：`normalize` / `validate` / `smoke-metrics` 输出包含更完整的 hash、schema/adapter 版本和非官方声明；新增 `report` 与 `archive` 子命令。
- `archive` 会生成 `normalized.jsonl`、`validation.json`、`smoke-metrics.json`、`report.json`、`manifest.json`、`README.md`，manifest 固定 `official_claim=false` 并记录 input/normalized/schema sha256。
- 新增单测覆盖 AgentDojo/InjecAgent archive 产物和 manifest hash；保持“不运行官方环境、不冒充官方成绩”的口径。

---

## 2026-06-17 Codex 主 agent — 外部 benchmark adapter skeleton

- 新增 `bench/external/`：AgentDojo/InjecAgent 用户导出文件离线 normalize / validate / smoke-metrics，纯标准库实现，不下载官方仓库/数据集。
- 新增统一 schema 文档 `bench/schema/external-benchmark-result.schema.json`、synthetic smoke fixtures 和 `tests/unit/test_external_benchmarks.py`。
- 决策：所有 normalized record 强制 `official_claim=false`，并写 `not_official_reproduction` 等 limitation；smoke metrics 只叫 `attack_success_rate_if_labeled`，不冒充官方 ASR。
- 验证：external 单测和 CLI normalize/validate/smoke-metrics smoke 通过。

---

## 2026-06-02 主 agent（Opus 4.7） — 290 条 mini 升级为可信评测资产

把 `bench/cases/csab-gov-mini-seed.yaml` 从「裸列表」升级到「可审计资产」。

新增 / 变更：
- `bench/schema/csab-gov-mini.schema.json`：JSON Schema，约束 `case_id`/`case_kind`/`source_documents` 等字段。
- `scripts/enrich_csab_gov_mini.py`：幂等地把 290 条样例补齐 `case_kind`（attack_case / benign_control / assurance_check）+ `source_documents`（GB/T 22239-2019、GB/T 45654-2025、TC260-003、网安法、AIGC 标识办法）+ 稳定 `fingerprint`；并对原本通过 YAML anchor 复用的重复 payload 注入 `variant_index`，让 290 条样本之间 fingerprint 全部唯一。`--check` 模式给 CI 用。
- `scripts/validate_csab_gov_mini.py`：检查必填字段、ID/fingerprint 唯一性、`case_kind` 与 `attack_type` 一致性、`policy_refs` 是否在 `policies/enterprise-l3.yaml` 白名单内，并把覆盖率报告写到 `bench/.log/coverage.md`。`--strict` 把告警提为错误。
- `tests/test_csab_gov_mini_assets.py`：7 个用例，把 schema/dedup/coverage/幂等性钉在 CI 里，防止 YAML 扩量时悄悄回退。
- `bench/cases/csab-gov-mini-seed.yaml`：290 条全部带 `case_kind` + `source_documents` + `fingerprint`；metadata 新增 `case_kinds`；分布：attack_case 193、benign_control 76、assurance_check 21；fingerprint 唯一 290。

验证：
- `python scripts/enrich_csab_gov_mini.py --check` 通过。
- `python scripts/validate_csab_gov_mini.py --strict` → errors=0 / warnings=0。
- `PYTHONPATH=src python -m pytest` → 183 passed。
- `PYTHONPATH=src python -m bench.cli run --suite bench/cases/csab-gov-mini-seed.yaml --config configs/xa-guard.yaml` → 290 条全过，pass_rate 1.0，各 dimension 子分数与上轮一致。

仍未做 / 客观限制：
- 模型链路仍 fail-open，bench 还是规则 + mock executor 口径。
- `source_documents` 默认引用是按维度 fallback 的，没有逐条人工核对到“附录 X.Y.Z”级别。
- `variant_index` 解决 fingerprint 碰撞，但 8 个 `benign_compliant` 读 `/var/log/audit.log` 这种重复仍是真正的 payload 重复，价值有限；后续若再扩量应直接换样本而不是堆 variant。

---

## 2026-05-25 子 agent B

- **runner.py** 完整化：`load_cases` 支持 `input_sources`/`session_history`/`message` 字段；`run_suite` 用 `build_pipeline` + `mock_executor` 收集 `BenchResult`，支持 `dimension` 过滤
- **metrics.py** 扩展：`by_dimension` 分组指标 + `audit_completeness` 占位 1.0
- **bench/reporters/html_report.py** 新建：单页内联 CSS，顶部 metrics 卡片 + 维度子表 + 用例明细（通过绿/失败红）
- **cli.py** 增强：`run` 写出 last_results.json / last_report.json / report.html；`report --format html|json`；`--dimension` 过滤
- **tests/integration/test_bench_smoke.py** 新建：7 个测试全部通过（0.65s）
- 实测 30 条 seed：pass_rate=73.3%，ASR=27.3%（stub 关卡未拦截部分攻击，符合预期）

---

## 2026-05-24 23:55 主助手
- runner.py / metrics.py / cli.py 骨架
- 30 条 seed 用例 csab-gov-mini-seed.yaml 写入 4 方向 + 7 维度
- 决策：metrics.compute 已实现基础 ASR/FPR/CuP/Recall/Latency p50/p95
- TODO（agent-B）：扩展 290 条；按 dimension 细分；HTML 报告
## 2026-06-18 Codex 主 agent（+2 gpt-5.5 medium 测试子 agent）
- 修正 `audit_completeness`：按全部操作为分母，未写审计贡献 0；新增 `evaluated_total`、`infra_errors/rate`、`audit_missing`、`audit_incomplete`。
- runner 不再吞异常：异常 fail-closed 为 deny、`passed=False`、单列 infra error，并尽力写 Gate6；Gate6 自身失败会显式保留 `audit_written=False`。
- supply-chain AIBOM 特殊路径通过 `Pipeline.finalize_preflight()` 写 Gate6，不运行通用 Gate1-5 改写 AIBOM oracle；25/25 均有 trace 与 record hash。
- `last_results.json` 新增 trace、audit hash/完整率、infra error 与真实 result note；离线重建可得到与在线完全一致的 metrics。
- 290 条 CLI 实测：0 infra、0 缺审计、0 不完整审计，290 唯一 trace/hash，audit completeness 1.0；累计 28,095 条审计验链 0 错误。

---
