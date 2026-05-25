# bench 模块工作日志

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
