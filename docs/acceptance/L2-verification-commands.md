# L2 验证命令（一键复现）

> 环境：Python 3.10+，仓库根目录执行。Windows PowerShell / Git Bash 均可。

## 0. 安装

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -e ".[bench,dev,policy,aibom]"
```

可选：Gate5 沙箱集成测试需 Docker Desktop + 本地镜像（见 §7）。

---

## 1. 全量 pytest

```bash
set PYTHONPATH=src
python -m pytest -q
```

期望：0 failed；可能 skip：缺少 `xa-guard/sandbox:latest`（1 条）、缺少 `tools/opa/opa.exe`（2 条）。

---

## 2. 测试覆盖率（L2 Hard ≥ 50%）

```bash
set PYTHONPATH=src
python -m pytest --cov=xa_guard --cov=bench --cov-report=term-missing --cov-report=html:htmlcov -q
```

报告目录：`htmlcov/index.html`。最新实测见 `status.md`「L2 工程完成」段。

---

## 3. XA-Bench 全量评测

```bash
set PYTHONPATH=src
python -m bench.cli run ^
  --suite bench/cases/csab-gov-mini-seed.yaml ^
  --config configs/xa-guard.yaml
```

输出：`bench/.log/report.html`、`bench/.log/last_report.json`（含 **实测** `audit_completeness`）。

---

## 4. Gate1-only 评测（含 Recall@FPR）

```bash
set PYTHONPATH=src
python scripts/evaluate_gate1.py --detectors rule
```

规则-only、Gate1 隔离口径；输出 JSON 含：

- `detectors_summary`（rule / model 子指标）
- `fusion` 相关 false negatives / positives
- `spotlighting_summary`
- `gate1_scope`（默认 6 类输入攻击 attack_type）
- `score_thresholds.recall_at_fpr`（Recall@1%FPR、Recall@5%FPR）

带 Qwen（需 GPU/权重）：

```bash
python scripts/evaluate_gate1.py --detectors rule,qwen --device cuda --dtype float16
```

---

## 5. 审计验链

先产生审计（bench 或 demo 场景），再验链：

```bash
set PYTHONPATH=src
python scripts/verify_audit.py --path logs/audit/audit.jsonl
```

---

## 6. 工具 × Gate 覆盖矩阵

```bash
python scripts/generate_tool_gate_coverage_matrix.py --strict --json
```

报告：`bench/.log/tool_gate_coverage.md`。

---

## 7. Gate3 规则 fixtures

```bash
python scripts/validate_gate3_rule_fixtures.py --strict --json
```

---

## 8. Gate5 沙箱镜像 + 集成测试

```bash
# Git Bash / WSL
bash scripts/build_sandbox_image.sh

# 或 PowerShell
docker build -f docker/sandbox.Dockerfile -t xa-guard/sandbox:latest .
```

```bash
set PYTHONPATH=src
python -m pytest tests/integration/test_sandbox_runner.py -q
```

期望：**1 passed，0 skipped**（镜像存在时）。

---

## 9. 演示场景（无 LLM）

```bash
set PYTHONPATH=src
python -m demo.scenarios.scenario_01_indirect_injection
python -m demo.scenarios.scenario_02_data_exfil
python -m demo.scenarios.scenario_03_hitl_approval
```

---

## 10. 推荐一次性 L2 冒烟链

```bash
set PYTHONPATH=src
python -m pytest -q --tb=short
python -m pytest --cov=xa_guard --cov=bench --cov-report=term -q
python scripts/evaluate_gate1.py --detectors rule
python scripts/generate_tool_gate_coverage_matrix.py --strict
python scripts/validate_gate3_rule_fixtures.py --strict
python -m bench.cli run --suite bench/cases/csab-gov-mini-seed.yaml --config configs/xa-guard.yaml
```

完整清单说明见 [`docs/acceptance/L2-acceptance-checklist.md`](./L2-acceptance-checklist.md)。
