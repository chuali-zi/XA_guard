# P2 脚手架设计（研究级靶场）

> 日期：2026-07-02
> 范围：仅 `enterprise-agent-range/` 独立靶场的 P2 骨架搭建。
> 约束来源：`docs/02-goals-and-scope.md`（P2 范围）、`docs/13-implementation-roadmap.md`（P2 路线）、`docs/04-decoupling-contract.md`（解耦契约）、`docs/05-architecture.md`（模块边界）。

## 目标

在 P1 完整靶场之上，为 P2 的 10 个研究级能力搭好**纯骨架**：目录、模块桩、接口/数据结构、能力注册表、文档与测试。本轮**不实现任何真实逻辑**，不改变 P0/P1 的运行行为与既有报告输出。

P2 的 10 个能力（对应 `docs/02` P2 范围）：

1. 多租户企业（tenancy）
2. Shadow AI 发现模拟（discovery）
3. Agent 身份生命周期（identity）
4. JIT/JEA/JLA 权限签发（permissions）
5. 风险金额量化（risk）
6. Undo / 补偿动作建议（remediation）
7. 大规模自动化 red-team runner（scale）
8. 外部 benchmark 与内部靶场融合（benchmark）
9. 第三方 TSA/HSM 证据链对接（evidence）
10. 攻防演练大屏和复盘报告（dashboard）

## 决策（已与用户确认）

- **深度：纯骨架。** 只有目录、模块桩、接口/dataclass、docstring、设计文档与测试。新能力的 oracle/metrics 以常量 + docstring 记录为"计划中"，不接入现有 oracle。
- **组织：新建 `range_src/enterprise_agent_range/p2/` 子包。** 一能力一模块，与 docs 的 10 项 1:1 可追溯。P1 模块保持不动。
- **覆盖：全部 10 项都建桩。**

## 架构与模块边界

```text
range_src/enterprise_agent_range/p2/
├── __init__.py          # 导出能力注册表与基础类型
├── base.py              # CapabilitySpec / CapabilityStatus / P2NotImplementedError
├── registry.py          # CAPABILITIES(10项) + capability_keys/get_capability/as_dicts
├── schema.py            # 聚合各 SPEC 的 planned_expected_fields/planned_metrics + PLANNED_CASE_FIELDS（均为“计划中，未接入 oracle”）
├── tenancy.py           # 1. Tenant / TenantRegistry（接口桩）
├── discovery.py         # 2. ShadowFinding / DiscoveryScan
├── identity.py          # 3. AgentIdentity + 生命周期状态
├── permissions.py       # 4. GrantRequest / IssuedGrant（JIT/JEA/JLA）
├── risk.py              # 5. RiskScore / RiskModel
├── remediation.py       # 6. CompensatingAction / UndoLog
├── scale.py             # 7. BatchPlan / Sharder（大规模 runner）
├── benchmark.py         # 8. BenchmarkRecord / BenchmarkAdapter（外部融合）
├── evidence.py          # 9. TimestampToken / TimestampAuthority / Signer（TSA/HSM）
└── dashboard.py         # 10. ExerciseFeed / ReviewReport（大屏 + 复盘）
```

每个能力模块统一模式：

- 若干 `@dataclass(frozen=True)` 数据结构，字段带类型与注释，用合成/占位单位（如风险金额用合成货币单位 `RANGE`，绝不涉及真实金额）。
- 一个接口类（普通类，方法体 `raise P2NotImplementedError(...)`），docstring 写明待实现内容 + 引用 docs 章节 + 预期 oracle/metrics。
- 一个模块级 `SPEC: CapabilitySpec`，供 `registry.py` 汇总。

`base.py`：

- `class CapabilityStatus`：常量 `SCAFFOLD="scaffold"` / `IN_PROGRESS` / `IMPLEMENTED` + `ALL`。
- `@dataclass(frozen=True) class CapabilitySpec`：`key, title, module, roadmap_refs, status, summary, planned_expected_fields, planned_metrics`，含 `to_dict()`。
- `class P2NotImplementedError(NotImplementedError)`：脚手架桩统一抛出的哨兵异常，便于测试锁定与后续 grep 替换。

## 与现有 runtime 的接入契约（关键：零行为变更）

- `p2` 是**纯 import 面**；`runner.py`、`oracles.py`、`reports.py`、`systems.py`、`models.py`、`adapters.py`、`tools.py`、`protocol.py`、`fixtures.py` **一律不改**。因此现有 `run` / `validate` / `compare` 输出逐字节不变。
- oracle **不新增 handler**，不改 `SUPPORTED_EXPECTED_FIELDS`（新增会影响 manifest 校验）。未来字段仅记录在 `p2/schema.py`。
- 唯一改动的旧文件是 `cli.py`：**新增** `p2-status` 子命令（懒加载 `p2.registry`，打印 10 项能力；支持 `--json`）。旧子命令与其行为不变。

## Case / Fixture / 报告脚手架（模板级，不进默认 run）

- `cases/p2_manifest.example.json`：带 `schema_version`、`metadata`、`capabilities`（10 项）、`planned_case_fields`、空 `fixtures`/`cases`。命名 `.example.json`，不被默认 `validate`/`run` 触碰。
- `fixtures/p2/README.md`：占位，说明未来 P2 fixture 归属与命名。
- 报告：`dashboard.py` 只定义 `ExerciseFeed`/`ReviewReport` 的数据结构桩，本轮不产出任何文件。

## 测试（保证 `unittest discover` 保持绿）

新增 `tests/test_p2_scaffold.py`：

1. 能 import `p2` 及全部子模块。
2. `CAPABILITIES` 恰好 10 项；key 集合等于预期 10 个；`status` 全为 `scaffold`；title 覆盖 docs 的 10 个能力。
3. 每个模块 `SPEC.key` 与 `SPEC.module` 自洽，且都被 `registry` 收录。
4. 每个能力接口的主方法调用抛 `P2NotImplementedError`（锁定“桩”契约）。
5. `schema.planned_expected_fields()/planned_metrics()` 与各 SPEC 一致。
6. `p2/` 源码内无 `import xa_guard` / `from xa_guard` / `src.xa_guard`（守解耦红线）。
7. `p2-status` CLI 返回 0，文本模式打印 10 行，`--json` 模式产出可解析 JSON。

现有测试文件不改。

## 解耦与红线（遵守 `docs/04`）

- 不 `import xa_guard`；不写入仓库根 `jiebang/src/`；不写入仓库根 `jiebang/docs/`。
- 所有新增文件都在 `enterprise-agent-range/` 内（`range_src/`、`cases/`、`fixtures/`、`docs/`、`tests/`）。
- 工作日志写入 `enterprise-agent-range/.log/worklog.md`（≤300 字）；`status.md` 追加 P2 脚手架条目。

## 明确不做（本轮）

- 不实现任何真实业务逻辑、不接 runner/oracle/report、不产新报告文件。
- 不新增运行时依赖（保持 `dependencies = []`）。
- 不写 P2 真实 case / fixture 数据。
- 不使用真实金额、真实密钥、真实 TSA/HSM、真实外部 benchmark 数据。

以上留给后续独立的实现计划（每个能力可作为一次 spec → plan → 实现循环）。

## 验收标准

- `python -m compileall range_src` PASS。
- `python -m unittest discover -s tests` PASS（含新增 `test_p2_scaffold.py`）。
- `python -m enterprise_agent_range validate --manifest cases/p1_manifest.json` 结果不变。
- `python -m enterprise_agent_range p2-status` 打印 10 项能力。
- `git diff` 确认除 `cli.py` 外未改动任何 P1 runtime 模块。
