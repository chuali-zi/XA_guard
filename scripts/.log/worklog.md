# scripts 工作日志

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
