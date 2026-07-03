# 红队靶场 Arena 重构计划（执行版）

> 范围：仅 `enterprise-agent-range/` 独立靶场。
> 目标：先把 arena 核心解耦成红队攻关平台，再做红队台工作流；不以扩题库为第一目标。

## 0. 实施状态

截至 2026-07-02 20:06 -07:00，阶段 A 的第一层 Arena Core 解耦和阶段 B 的最小 CLI 红队台已实现：

- 已拆出 `WorldSpec`、`ChallengeSuite`、`ToolSurface`、`PolicyOverlay`、`EvidenceStore`、OpenCode agent seat、XA-Guard SUT adapter、redteam `Finding`。
- `arena/live.py` 已变成兼容入口并接入 `EvidenceStore`，不再独占所有路径和 SUT 配置生成职责。
- 已新增 `arena worlds|surfaces|challenges|init-finding|promote|show|run-ab` 命令组；旧 `arena-live`、`finding-init`、`finding-promote` 仍保留。
- 本轮只跑本地非 live 验证，未运行真实 OpenCode/GLM live 调用。
- 未完成项：attempt/report -> regression promotion、live N 次统计报告、多企业域扩展、旧 242 P1 case 迁移。
## 1. 目标判断

用户当前目标不是让实现者替红队成员继续出题，而是搭建一个红队成员能快速理解、攻关、复现、固化 findings 的靶场平台。

因此本轮重构优先级为：

1. `arena/` 核心解耦和通用化。
2. 红队攻关工作流和最小红队台能力。
3. 红队成员上手文档和证据查看路径。
4. 后续才是迁移旧 case、扩展 ops/data/dev/audit 域或做大规模统计。

## 2. 当前基线

已具备：

- P0/P1 静态回放路径：`cases/p0_manifest.json`、`cases/p1_manifest.json`、`python -m enterprise_agent_range run`。
- P1 规模：242 cases、66 mock tools、JSON/JSONL/Markdown/HTML 报告。
- `arena/` office/mail 竖切：`World + Challenge + Injection + AgentSeat + SUT + Oracle + Live runner`。
- live 证据：OpenCode -> XA-Guard stdio MCP -> office/mail MCP server；attack+guard 拦截，attack+null 泄漏，control 双路径通过。

必须承认的边界：

- live 仍是 N=1 smoke，不是统计评测。
- 当前可运行 world/surface 仍只有 bounded office/mail baseline，其他企业域尚未接入。
- 旧 242 cases 尚未迁入 Challenge schema。
- 红队成员已有最小 CLI 工作台，但还没有 Web UI、报告层或从 live attempt 自动固化 regression 的流程。

## 3. 非目标

本阶段不做：

- 不优先扩展新题库或替红队成员写攻击题。
- 不一次性迁移 242 个旧 case。
- 不删除 P0/P1 回放 runner。
- 不实现真实生产邮件、生产 API、真实外发、真实密钥或真实 HSM/TSA。
- 不把靶场 runtime 放入仓库根 `src/`。
- 不为通过靶场而修改 XA-Guard 主产品策略或测试。

## 4. 阶段 A：Arena Core 解耦重构

目标：把 office/mail 竖切里已经跑通的结构沉淀成通用核心，而不是继续让 `live.py` 承担所有职责。

### A1. 固定核心对象

新增或整理以下接口，保持纯 stdlib 和可单测：

| 对象 | 责任 |
|---|---|
| `WorldSpec` / `WorldFactory` | 定义可复用企业环境，不属于题目。 |
| `Challenge` | 只包含 `world`、`inject`、`task`、`oracle`，禁止 `execution.steps`。 |
| `InjectionTarget` | 支持 `mailbox:`，为后续 `log:`、`rag:`、`plugin:` 预留。 |
| `ToolSurface` | 描述 world 暴露哪些工具、schema、风险和副作用 sink。 |
| `AgentSeat` | Live agent、Replay agent、未来 redteam 手动 seat 的统一边界。 |
| `SUTAdapter` | Null、GuardStub、外部 XA-Guard、未来其他代理的统一边界。 |
| `Oracle` | 只读取 world side effects、SUT audit、transcript，不反推 SUT 策略。 |
| `EvidenceStore` | 管理每次 attempt 的 transcript、tool events、audit、effects、verdict、hash。 |

### A2. 拆分 `arena/live.py`

建议拆成：

```text
arena/
├── live_suite.py          # suite 编排、repeat、run manifest
├── opencode_seat.py       # OpenCode headless agent seat
├── sut_xaguard.py         # 生成 XA-Guard 临时配置并作为外部进程启动
├── evidence.py            # AttemptEvidence / EvidenceStore / artifact hashes
├── policy_overlay.py      # 从 challenge/world 配置生成临时 Gate3/Gate4 文件
└── live.py                # 兼容薄入口，避免 CLI 立即破坏
```

### A3. 去硬编码

- `default_challenge_paths()` 不再写死 `OFFICE-INJ-001`，改成读取 suite 或目录 manifest。
- Gate3 live overlay 不再写死 Atlas 预算关键词，改由 challenge/world 的 `policy_fixture` 或 `sensitive_markers` 生成。
- Gate4 capability 不再只追加 `read_mail/query_project`，改由 `ToolSurface` 导出。
- attempt 目录命名不再用 `case-001.case/path-a/path-b` 这类含义不清的标签，改成 `challenge_id/kind/sut_mode/attempt-NNN`。

### A4. 验收标准

- `python -m unittest discover -s tests -v` 通过。
- P1 validate/run 仍通过，242 cases 不被破坏。
- `arena-live --sut-mode both --repeat 1` 仍能复现原 office/mail 2x2 smoke。
- `rg "import xa_guard|from xa_guard" enterprise-agent-range/range_src/enterprise_agent_range` 无命中。
- 新增 Challenge 不需要写 `execution.steps`。

## 5. 阶段 B：红队攻关工作流

目标：让红队成员不用读完整源码，也能完成“看靶场 -> 攻关 -> 复现 -> 提交 finding -> 固化回归”。

### B1. 最小 CLI 工作台

建议新增 `arena` 子命令组：

```powershell
python -m enterprise_agent_range arena worlds
python -m enterprise_agent_range arena surfaces --world office-baseline
python -m enterprise_agent_range arena challenges
python -m enterprise_agent_range arena init-finding --world office-baseline --target mailbox:bob.employee@range.local
python -m enterprise_agent_range arena run-ab --finding findings/<id>.json --sut-mode both --repeat 1
python -m enterprise_agent_range arena show reports/<run>/...
python -m enterprise_agent_range arena promote --finding findings/<id>.json --out cases/arena/<id>.attack.json
```

第一版可以只做 CLI，不做 Web UI。

### B2. Finding schema

红队成员提交的是 finding，不是正式 case：

```json
{
  "finding_id": "FIND-YYYYMMDD-001",
  "world": "office-baseline",
  "target": "mailbox:bob.employee@range.local",
  "payload_ref": "findings/payloads/FIND-YYYYMMDD-001.md",
  "task_prompt": "中性任务，不写攻击结果",
  "expected_risk": ["AT2.1", "AT3.1"],
  "notes": "红队成员观察"
}
```

runner 将 finding 临时转换为 Challenge 执行；只有通过审核的 finding 才 `promote` 成 `cases/arena/*.json`。

### B3. 红队成员可见材料

- 靶场地图：world、principal、tool、data asset、sink。
- 攻击面说明：可以投毒哪些入口，哪些副作用会被捕获。
- 证据阅读说明：怎么看 transcript、tool events、audit、effects、verdict。
- 固化规则：什么情况下 finding 可以进入 regression。

## 6. 阶段 C：报告和统计轨

目标：让红队台既能看单次攻关证据，也能看 A/B 差值。

- `repeat N` 结果聚合为 attempt 表，不把 INFRA_ERROR 算进安全分母。
- guard/null 分开报告，并计算 `ASR_null - ASR_guard`。
- 攻击、良性、assurance 分开分母。
- 输出 JSON/Markdown/HTML/hash；人工 finding 不混入自动化指标。
- N=1 只能标记为 smoke；N>1 才能写统计口径，并带置信区间。

## 7. 阶段 D：迁移和扩域

前置条件：A/B/C 稳定后再做。

顺序建议：

1. office/mail 旧 case 分桶迁移。
2. ops 日志注入 world。
3. data/RAG world。
4. dev-supply/plugin world。
5. audit/tamper world。

迁移原则：旧 P1 manifest 保留，新增 arena case 使用 Challenge schema；迁一个域，保留对应的良性对照和 smoke 证据。

## 8. 审核问题

请确认：

1. 阶段 A 是否可以作为下一轮代码重构唯一目标？
2. 红队台第一版是否接受 CLI 优先，Web UI 后置？
3. Finding schema 是否符合红队成员提交方式？
4. 是否允许我在阶段 A 中重命名/拆分 `arena/live.py`，但保留兼容 CLI？
5. live 真实 OpenCode N 次运行是否必须单独授权，默认只跑单元测试和结构验证？