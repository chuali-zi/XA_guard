# 仓库状态 · XA-Guard / XA-202620

> 本文件描述**当前仓库状态**（差什么、需要改什么、距 PRD 还有多远），不是工作日志。
> 工作流水记 `log.md`；L2 冻结清单见 `docs/L2-acceptance-checklist.md`；验证命令见 `docs/L2-verification-commands.md`。
> 快照时间：2026-06-16 +08:00

---

## 一句话定位

**L2 工程完成（Hard + Competition-trusted 口径）**：6 关卡 pipeline 可跑、394 pytest 全绿（0 skip）、**覆盖率 82%**（≥50% L2 Hard）、290 条 XA-Bench、Gate1-only evaluator、覆盖矩阵、Gate3 fixtures、Gate5 Docker sandbox smoke、审计验链、**bench `audit_completeness` 由 Gate6 记录实测**。仍是 demo MVP，**不是 PRD L3 政企原型**。

---

## L2 工程完成（客观陈述）

| 维度 | 状态 | 证据 |
|---|---|---|
| **Hard L2（PRD §4.2）** | ✅ | LOC ≈ 7900+（src+bench）；README 已对齐当前策略目录与命令；`pytest --cov` **82%**；6 关单元测试齐全 |
| **全量 pytest** | ✅ 394 passed / 0 skipped | `PYTHONPATH=src python -m pytest -q` |
| **XA-Bench 290** | ✅ | `python -m bench.cli run …` → pass_rate 100%，`audit_completeness=1.0`（265 条走 pipeline 写审计） |
| **Gate1-only evaluator** | ✅ | `python scripts/evaluate_gate1.py --detectors rule`；Gate1-scope 60 attack：Recall **68.33%**，FPR blocking **0**；含 `recall_at_fpr` |
| **覆盖矩阵** | ✅ | `--strict`：tools=48 / gate2=48 / gate4=48 / bench_only=0 |
| **Gate3 fixtures** | ✅ | 31 规则 × 正/反例，`validate_gate3_rule_fixtures.py --strict` errors=0 |
| **审计完整率** | ✅ 已实测 | `bench/metrics.py` 聚合 Gate6 `audit_completeness`；非固定占位 |
| **Gate5 沙箱镜像** | ✅ 本机已构建并实测 | Docker Desktop 已启动；`docker build -f docker/sandbox.Dockerfile -t xa-guard/sandbox:latest .`；`tests/integration/test_sandbox_runner.py` 真实执行通过 |

**Competition-trusted L2 当前已闭合**：真实 Qwen GPU 复跑 Gate1、真实 IDE HITL 截图归入 L3/冲刺证据——见 L3 段。

---

## 测试状态

- `PYTHONPATH=src python -m pytest -q --basetemp pytest_tmp_full_after_sandbox -p no:cacheprovider -x --tb=short`：**394 passed / 0 skipped / 0 failed**
- Gate5 sandbox：已构建本机镜像 `xa-guard/sandbox:latest`；`tests/integration/test_sandbox_runner.py` 真实执行通过，验证禁网 + 只读 rootfs
- OPA：`tools/opa/opa.exe` 若存在则 Gate3 OPA 测试不 skip（视本机是否已下载）
- 覆盖率：`PYTHONPATH=src python -m pytest --cov=xa_guard --cov=bench --cov-report=term -q` → **TOTAL 82%**

---

## 策略与关卡（摘要）

- **双层策略**：`policies/baseline/` + `overlay/`；`LayeredPolicySource` 合并；risk_level 唯一源 `gate4_capabilities.yaml`
- **Gate1**：规则 + 可选模型；Spotlighting metadata 可审计；Gate1-only evaluator 拆分 rule/model/fusion/spotlighting
- **Gate2–5**：风险分级 / 31 条 Gate3 / 污点 / 沙箱路由（Docker 命令构造已实现）
- **Gate6**：OTel JSONL + 哈希链；`audit_completeness` 按 CORE 字段完整率计算

---

## 距 PRD 目标

| 级别 | 状态 |
|---|---|
| **L1 基础** | ✅ 满足 |
| **L2 工程** | ✅ **Hard 项满足**；Competition-trusted 证据闭合 |
| **L3 政企** | ❌ 未达——见下节 |
| **L4 工业** | ❌ 未开始 |

---

## L3 差距（与 L2 清单明确分离）

1. **Docker Compose 一键部署**、生产级国密 SM2/SM3 + TSA
2. **Trae / 国产 IDE 真实 HITL 弹窗**实测与截图
3. **AgentDojo / InjecAgent** 外部 benchmark 对照；Recall@1%FPR 达 PRD 中等档（95%）
4. **layered 策略接 OPA Rego** 合并视图；gVisor Linux 实测
5. **bench supply_chain 接 `gateway.admit()`**；真实 MCP 安装链路
6. **500+ 国标完整题库**；30 页 PDF / 10 分钟视频 / 报名表
7. **Streamable HTTP 上游**；LangChain SDK 非透传；CoT faithfulness 实算法

---

## 赛题四方向贴合（简表）

| 方向 | L2 现状 | L3 主要空位 |
|---|---|---|
| 1 输入攻击 | 规则 + Gate1 evaluator + Qwen 代码路径 | 模型主检测能力、自适应攻击集 |
| 2 工具安全 | Gate2–5 + layered + MCP E2E 测试 | 真实客户端 UI、OPA layered |
| 3 供应链 | AIBOM 5 项生产化 + CLI | bench/MCP 接 gateway、实时 feed |
| 4 评测审计 | 290 bench + 实测 audit + 前端 | 外部 benchmark、正式国密链 |

---

## 下一步（L3 导向）

1. Gate1：Recall@1%FPR 达标路径（更大模型 / 专门 MCP 分类器 / 扩充规则）
2. 真实 Trae HITL 证据链
3. Docker Compose 一键部署与 Linux/gVisor 实测
4. 交付物：PDF / 视频 / 报名
