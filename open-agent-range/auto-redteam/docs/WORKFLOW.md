# WORKFLOW · 战役生命周期状态机

## 概念层级

```
Campaign（一次攻坚战役）
 └── Objective（一个目标 = 7类攻击之一 × 某个 OAR 开放面）   ← objectives.py 队列
      └── Run（一次本地 CLI proposal + Conductor A/B 执行）
           └── Attempt（一次 run-ab，含 Null 裸奔 + xaguard 防御 两跑）
```

## 单目标状态机

```
        ┌────────┐
        │  INIT  │  从 objectives.next() 取目标，装配本地 mission pack
        └───┬────┘
            ▼
        ┌────────┐  local CLI engine 读取 propose-payload.md
        │ PROPOSE│  本地 Cursor/OpenCode/Codex 串行生成 JSON proposal
        └───┬────┘
            ▼
       ┌─────────┐  schema/scope/novelty；拒绝越界与重复 payload
        │  CHECK  │ scope + novelty + strategy lane 去重
       └────┬────┘              │（超时/error/QUOTA）
            ▼                    ▼
      ┌──────────┐         ┌──────────┐
       │ RUN-AB   │         │  HALT    │  breaker：连续失败/配额耗尽→暂停该目标
      └────┬─────┘         └──────────┘
      win?  │  miss/reject?
    ┌──────┴───────┐
    ▼              ▼
┌────────┐   预算(轮数/USD)还够?
│  WIN   │    ┌────┴─────┐
└───┬────┘    ▼          ▼
    │      ┌────────┐  ┌────────┐
    │      │ REFINE │  │ CLOSE  │  记为"未攻破"，沉淀负样本证据
    │      └───┬────┘  └───┬────┘
    │          │（重新分配不同 strategy lane）
    │          └──────────► PROPOSE
    ▼
┌─────────┐  promote.py：本地 run 目录写 PROMOTE.md
│ PROMOTE │
└───┬─────┘
    ▼
┌─────────┐  evidence_sync.seal() + provenance-manifest.jsonl(git add)
│  SEAL   │
└───┬─────┘
    ▼
NEXT_OBJECTIVE ──► objectives.mark_covered() ──► INIT（下一目标）
```

## 状态说明

| 状态 | 动作 | 退出条件 |
|---|---|---|
| INIT | 取目标，装配种子提示（world + surface + 攻击分类 + 安全横幅） | 提示就绪 |
| PROPOSE | 本地 CLI 读取 mission pack，返回 attack proposal JSON | proposal schema 可解析 |
| CHECK | `scope.py` + `novelty.py` 拦截越界和重复 payload | accepted / rejected |
| RUN-AB | Conductor 写 finding 并调用 `kernel.workbench run-ab --execute` | 生成 summary/evidence |
| EVALUATE | `evaluator.judge(summary.json)` | 得到 win/miss + 指纹/block_reason |
| REFINE | 依 block_reason 分配不同 strategy lane，不暴露成功 payload 正文 | 新 proposal |
| WIN | 标记攻破，触发 promote | — |
| PROMOTE | findings 分支提交 + 建 PR | PR 建成或提交完成 |
| CLOSE | 记未攻破，保留负样本证据（对回归同样有价值） | — |
| SEAL | 封存证据 + 写溯源清单 | tar+sha256+manifest 完成 |
| HALT | breaker：连续 N 次 error 或配额耗尽，暂停该目标并告警 | 人工/定时恢复 |

## 预算与退出（三重护栏，详见 SAFETY-AND-BUDGET.md）

单目标退出 REFINE 的条件（任一触发即 CLOSE）：
- `max_refines_per_objective` 轮数用尽；
- 该目标累计 `usage`（token→USD 估算）超过 `per_objective_usd`；
- 全局 `budget_usd` 剩余不足以再起一轮。

Campaign 退出（CAMPAIGN_DONE）：目标队列遍历完 / 全局 `budget_usd` 耗尽 / 收到 `--stop`。

## 持续模式（`--continuous`）

```
while not stop_flag and budget_left:
    objective = objectives.next()          # 覆盖度优先 + novelty 加权
    if objective is None:                  # 队列空 → 重新生成新一轮目标网格
        objectives.replenish()             # 提升 novelty 门槛，避免重复
        continue
    run_objective_state_machine(objective)
```

可由 **Windows 任务计划 / cron** 定时拉起（参照 `tools/remote-runner/windows/register-task.md` 的 schtasks 做法），实现"持续攻坚"。每次拉起先 `load_state()` 幂等续跑，不重复已封存的 run。

## 幂等与断电安全（借鉴 supervisor.py）

- 每个状态转移后原子写 `state.json`（写临时文件 + `os.replace`）。
- run 与 objective 以 `run-id` / `objective-id` 去重；重启后跳过已 SEAL 的。
- `--stop` 写 stop_flag 文件，主循环在安全点（两次 run 之间）优雅退出；local 模式没有脱离本机的云端 run。

## Dry-run（`--dry-run`，零花费）

不发任何真实请求，打印：① 完整目标队列（7 类 × 开放面）；② 每个目标将注入的种子提示全文；③ 预算账本（预计最大 run 数、USD 上限）；④ 证据落盘路径预览。用于评审"它到底会干什么"。
