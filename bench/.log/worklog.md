# bench 模块工作日志

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
