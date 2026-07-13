# ARCHITECTURE · 两层自动红队架构

## 设计原则

1. **判定权归靶场，不归 LLM**：胜负永远由 OAR 的 ledger + oracle/property + accountability 裁定，绝不让 CLI agent 自评"我攻破了"。这规避了 [2025-AutoInjectAgentic](../../../docs/references/literature/06_agent_redteam/2025-AutoInjectAgentic.md) 点名的"判定器噪声"风险。
2. **模型只提案，Conductor 执行**：Cursor/OpenCode/Codex 只返回 JSON proposal。Conductor 做 scope、novelty、finding 写入、A/B 执行、评估、证据和晋级标记。
3. **严格串行**：`max_active_agents=1`，三 CLI 轮转但不并行，避免同时生成重复 payload 或抢占同一策略车道。
4. **不改靶场内核**：本工作流只**调用** `python -m kernel.workbench`，绝不修改 `kernel/`、`scenarios/dctg/`、测试或 XA-Guard 策略。对齐 remote-runner"只包裹不修改"原则。

## 两层

```
┌─────────────────────────────────────────────────────────────────────┐
│  Tier 1 · 本地 Conductor（战役管理器，纯 Python，无 LLM）              │
│                                                                       │
│  objectives.py  ── 7类攻击 × OAR开放面 目标队列（覆盖度/novelty 加权） │
│  conductor.py   ── 主循环：ASSIGN→PROPOSE→CHECK→RUN-AB→EVALUATE       │
│  cursor_client.py ─ api.cursor.com/v1 薄 REST 客户端（SSE/artifacts） │
│  engines.py     ── Cursor Agent CLI / OpenCode / Codex proposal 后端  │
│  scope.py       ── 安全边界校验：只允许 OAR 合成靶场                 │
│  novelty.py     ── exact/similarity/strategy-lane 去重               │
│  evaluator.py   ── 解析 OAR verdict/ledger → 胜负 + novelty           │
│  evidence_sync.py ─ 拉 artifacts → 七件套 → git 锚定溯源封存           │
│  promote.py     ── 胜出 finding 自动提交 findings 分支 + 建 PR         │
│  state（JSON）  ── campaign 状态持久化，断电安全/幂等续跑              │
└───────────────┬───────────────────────────────────────▲──────────────┘
                │ POST /v1/agents · POST .../runs         │ GET .../artifacts
                │ GET .../runs/{id}/stream (SSE)          │ GET .../runs/{id}
                ▼                                         │
┌─────────────────────────────────────────────────────────────────────┐
│  Tier 2 · 本地 CLI Agent（proposal-only，独立 mission pack）           │
│                                                                       │
│  由 prompts/propose-payload.md 注入契约：                              │
│   1. 只读 mission context / prior-art 摘要 / schema                   │
│   2. 依 7 类分类学造一个 JSON proposal                                │
│   3. 不执行 shell、不联网、不写仓库、不建 PR                           │
│   4. Conductor 验证通过后本地 run-ab                                  │
└─────────────────────────────────────────────────────────────────────┘
```

## 组件职责

### conductor.py — 主循环
把 [WORKFLOW.md](./WORKFLOW.md) 的状态机跑起来：从 `objectives.py` 取下一个目标 → 轮转选择一个本地 CLI engine → 渲染 `propose-payload.md` mission pack → scope/novelty 检查 → 写 finding → 调 `kernel.workbench run-ab` → `evaluator` 判胜负 → `evidence_sync` 封存 → 下一个目标。每步落盘 state，支持 `--stop` 与断点续跑。

### engines.py / scope.py / novelty.py — 本地 proposal 闭环
`engines.py` 封装 Cursor Agent CLI、OpenCode 和 Codex 的 proposal-only 调用；`scope.py` 拒绝越界目标、公网 URL/IP、非合成邮箱和 objective 不匹配；`novelty.py` 维护 exact/similarity/strategy-lane registry，防止三个 agent 复用已有成功 payload。

### cursor_client.py — Cloud opt-in 旧 REST 客户端
薄封装 `https://api.cursor.com/v1`（详见 [CURSOR-API-INTEGRATION.md](./CURSOR-API-INTEGRATION.md)）。当前默认不使用 Cloud；仅在 `engine: cloud` 显式开启时作为旧后端保留。

### objectives.py — 目标队列
维护 `7 类攻击 × OAR 开放面` 的目标网格（见 [THREAT-MODEL.md](./THREAT-MODEL.md)），按"覆盖度优先 + novelty 加权"选下一个目标（思想来自 [2026-PISmith](../../../docs/references/literature/06_agent_redteam/2026-PISmith.md)）：未覆盖的格子优先，重复 payload 指纹降权。

### evaluator.py — 胜负判定
只读 OAR 产物：从 A/B `summary.json` / `verdict.json` / `ledger-replay.json` / `accountability-report.json` 判定"是否达成坏状态（泄漏/越权/不可追责）且仅在 NullSUT 达成而 xaguard 拦截"。产出结构化战果 + payload 指纹（用于 novelty）。**不调用 LLM。**

### evidence_sync.py — 证据落盘
把本地 mission、proposal、finding、A/B evidence 组织为标准 run 目录，调 `tools/evidence/seal-run.sh` 封存，追加写 git 锚定的 `provenance-manifest.jsonl`。

### promote.py — 自动晋级
攻破或被拦截但 NullSUT 成立的 finding，在 evidence run 目录写 `PROMOTE.md` 标记。local 模式不让模型提交分支或建 PR；向 `main` 的合并保留为人/CI 确定性步骤。

## 数据流（一次攻破的完整链路）

```
objectives.next() ──► conductor.ASSIGN
      │ propose-payload.md + mission context + prior-art summary
      ▼
local CLI engine returns proposal.json
      ▼
scope.py + novelty.py gate
      ▼
Conductor writes finding.json and runs kernel.workbench run-ab
      ▼
evaluator.judge(summary.json) ──► {win: true, risk: sensitive-egress, fingerprint: ...}
      ▼  win
promote.record_promotion() ──► PROMOTE.md
      ▼
evidence_sync.seal() ──► sealed/<run-id>.tar.gz + provenance-manifest.jsonl(git add)
      ▼
objectives.mark_covered() ──► conductor.NEXT_OBJECTIVE
```

未攻破或被 scope/novelty 拒绝时，Conductor 记录原因并在后续目标/refine 中分配不同 strategy lane；不会把已有成功 payload 正文再次交给 agent。

## 时序图（自适应闭环）

```
Conductor        Local CLI Agent        Scope/Novelty        OAR CLI
   │ mission pack ──►│
   │◄─ proposal.json │
   │──────────────────────────────► gate
   │◄────────────────────────────── accepted/rejected
   │ write finding.json ───────────────────────────────────►│
   │ run-ab --execute ─────────────────────────────────────►│
   │◄──────────────────────────────────── summary/evidence   │
   │ judge + seal + provenance
```

## 与既有资产的复用
- **OAR CLI**：`kernel/workbench.py`（worlds/surfaces/init-finding/validate-finding/run-ab/review-finding/promote）——攻击执行与判定的唯一入口。
- **证据规范**：`docs/acceptance/remote-evidence/EVIDENCE-LAYOUT-SPEC.md` + `tools/evidence/*.sh`——证据封存与溯源。
- **断电安全编排模式**：`tools/remote-runner/supervisor.py`——state 持久化、幂等续跑、breaker 的参考实现。
- **红队安全规则**：`open-agent-range/docs/redteam/REDTEAM-AGENT-TECHNICAL-MANUAL.md` §14。
