# L2 验收清单（冻结口径）

> 快照：2026-06-16 · 依据 [`docs/planning/PRD.md`](../planning/PRD.md) §4.2「4 级完成度」与赛题 D2 要求
> **本清单只覆盖 L2 工程完成度**；L3 政企 / L4 工业项明确排除，见文末。

---

## A. Hard L2（PRD 定义，可勾选验收）

PRD §4.2：**L2 工程 = L1 基础 + 测试覆盖率 ≥ 50% + 详细 README**。

| # | 项 | 门槛 | 验证命令 / 证据 |
|---|---|---|---|
| A1 | **LOC** | ≥ 3000（不含 vendor） | `find src bench -name '*.py' \| xargs wc -l` 或 IDE 统计 |
| A2 | **README** | 含介绍、架构、快速开始、配置、FAQ、当前限制 | 根目录 [`README.md`](../../README.md) |
| A3 | **测试覆盖率** | ≥ 50%（`pytest --cov`） | 见 [`docs/acceptance/L2-verification-commands.md`](./L2-verification-commands.md) §覆盖率 |
| A4 | **6 关卡单元测试** | 每关 `tests/unit/test_gateX*.py` 存在且可跑 | `PYTHONPATH=src pytest tests/unit/test_gate1*.py … test_gate6*.py -q` |
| A5 | **全量 pytest** | 0 failed（允许环境 skip：Docker 镜像 / OPA） | `PYTHONPATH=src pytest -q` |
| A6 | **公开仓库 + LICENSE** | Apache-2.0（或团队确认） | 根目录 LICENSE / README |
| A7 | **Policy baseline** | ≥ 30 条 Gate3 规则 + 正/反例 fixtures | `python scripts/validate_gate3_rule_fixtures.py --strict` |

**L2 Hard 判定**：A1–A7 全部满足 → PRD「L2 工程」Hard 项达标。

---

## B. Competition-trusted L2（比赛可信证据，非 PRD Hard 但答辩/评审常用）

这些项**不计入 PRD Hard L2**，但仓库应能**一条命令复现**并写进 `status.md` / bench 报告。

| # | 项 | 说明 | 验证命令 / 证据 |
|---|---|---|---|
| B1 | **XA-Bench 290 条** | CSAB-Gov-mini seed + CLI + HTML | `python -m bench.cli run --suite bench/cases/csab-gov-mini-seed.yaml --config configs/xa-guard.yaml` |
| B2 | **Gate1-only 评测** | 拆分 rule / model / fusion / spotlighting；含 Recall@FPR 口径 | `python scripts/evaluate_gate1.py --detectors rule` |
| B3 | **工具×Gate 覆盖矩阵** | layered-merged 视图，`--strict` 无缺口 | `python scripts/generate_tool_gate_coverage_matrix.py --strict` |
| B4 | **审计哈希链** | `verify_audit.py` 验链 + 字段 | `python scripts/verify_audit.py --path logs/audit/audit.jsonl` |
| B5 | **bench 审计完整率** | 由 Gate6 记录实测，非固定 1.0 | bench 报告 `audit_completeness` 字段 |
| B6 | **HITL / elicitation 证据** | toy probe + MCP E2E 测试；真实客户端 UI 截图另计 | `tests/integration/test_mcp_e2e.py` + `docs/tutorials/HITL-elicitation-toy-probe.md` |
| B7 | **Gate5 沙箱 smoke** | `xa-guard/sandbox:latest` 禁网 + 只读 rootfs | 构建镜像后 `pytest tests/integration/test_sandbox_runner.py -q` |
| B8 | **Gate3 fixtures** | 32 条 baseline 每条 1 正 1 反 | `python scripts/validate_gate3_rule_fixtures.py --strict` |

**Competition-trusted 判定**：B1–B5 + B7–B8 可复现；B6 至少具备代码/文档证据（真实 IDE 弹窗为 L3 增强）。

---

## C. 明确排除（属于 L3+，不在本清单）

以下 PRD / 赛题项**不属于 L2 冻结范围**，勿与 L2 完成混淆：

| 排除项 | 目标级别 |
|---|---|
| Docker Compose 一键部署 | L3 政企 |
| 真实国密 SM2/SM3 + TSA 证据链 | L3 政企 |
| Trae / 国产 IDE 真实接入截图 | L3 政企（PRD Must，但 Hard L2 未单列） |
| AgentDojo / InjecAgent 完整复现 | L3 / 冲刺 KPI |
| 500+ 国标完整题库 | L3–L4 |
| 30 页 PDF / 10 分钟视频 / 报名表 | 赛题交付物（非代码 L2） |
| CI/CD + 监控告警 | L4 工业 |
| layered 策略接 OPA Rego 合并视图 | L3 |
| AIBOM gateway 接 bench supply_chain | L3 生产化 |

---

## D. 一句话结论模板

> **L2 Hard（PRD）**：6 关可跑 + pytest 全绿 + 覆盖率 ≥ 50% + README 完备 + Gate3 fixtures 强约束。  
> **L2 Competition-trusted**：290 bench + Gate1 evaluator + 覆盖矩阵 + 审计验链 + 沙箱镜像 smoke + 实测 audit_completeness。  
> **未到 L3**：一键部署、真实国密、真实客户端 HITL、外部 benchmark 对照、完整合规映射。

维护：状态变更时同步更新 [`status.md`](../../status.md)；执行记录写 [`log.md`](../../log.md)。
