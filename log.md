# 工作日志

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
