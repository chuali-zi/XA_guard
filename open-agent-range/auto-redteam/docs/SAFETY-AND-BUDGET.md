# SAFETY-AND-BUDGET · 安全边界与预算护栏

## 授权与定位

本工作流是**对团队自有资产的授权防御性红队测试**：攻击目标是本仓库内的**合成靶场 OAR**，被测防御是团队自研的 **XA-Guard**（挑战杯 XA-202620 参赛作品）。目的是暴露并修复自有防护的缺口。不针对任何第三方系统。

## 硬性安全规则（继承 REDTEAM 手册 §14）

1. **纯合成数据**：只操作 OAR 的合成 DCTG 世界。禁止真实凭据、真实个人信息、真实密钥。
2. **无公网目标**：payload 的"外发接收方"只能是 OAR 世界内的合成实体（如"甲方-政府客户"），**绝不**是真实邮箱/域名/IP/webhook。
3. **无真实副作用**：所有工具调用在 OAR 沙盘内，不触真实文件系统外的东西、不发真实网络请求。
4. **不改内核**：只 `python -m kernel.workbench` 调用；不修改 `kernel/`、`scenarios/dctg/`。新增仅限 `scenarios/injections/*.json`。
5. **不让模型写 Git**：local 模式下 CLI agent 不提交、不推送、不建 PR；Cloud 旧后端显式 opt-in 时也不得推 `main`。

## 主干安全（proposal-only 本地自治）

默认不再让 agent 写仓库或建 PR。Cursor/OpenCode/Codex 只生成 proposal JSON，Conductor 在本地写 finding/evidence，并只落 `PROMOTE.md` 标记。向 `main` 的合并仍是确定性步骤（人工 review PR / CI），不是模型自治行为。

## 预算护栏（三重）

| 层 | 机制 | 配置项 |
|---|---|---|
| 1. Conductor 全局 | 累计 `usage` token→USD 估算，超 `budget_usd` 即停止起新 run | `budget_usd` |
| 1. Conductor 单目标 | 每目标 USD 上限 + 最大自适应轮数 | `per_objective_usd` / `max_refines_per_objective` |
| 1. Conductor 单 run | 本地子进程超时即终止并封存 INFRA_ERROR | `run_timeout_s` |
| 2. Provider 面板 | Cursor/OpenCode/Codex 对应账户级 spend limit（兜底） | — |
| 3. 数量 | 全局最大 agent 数 / 最大 run 数 | `max_agents` / `max_runs` |

USD 估算：`est_usd = f(totalTokens, model_price)`；模型单价在 `config` 里可配，宁可高估以早停。

## Kill switch

```bash
python -m conductor.conductor --stop
```
写 `state/stop.flag` → 主循环在下一个安全点优雅退出。local 模式没有云端后台任务；Cloud opt-in 旧后端才需要 cancel/archive。

## 幂等 / 断电安全（借鉴 remote-runner supervisor）

- 每次状态转移原子写 `state.json`（temp + `os.replace`）。
- 重启 `load_state()` 续跑，跳过已 SEAL 的 run/objective。
- `--continuous` 定时拉起时不重复消耗预算。

## Breaker（防失控烧钱）

连续 `breaker_max_errors` 次 run 返回 error/QUOTA，或单位时间花费斜率超阈值 → 该目标转 HALT 并告警（写 `ALERTS`），不再自动起新 run，需人工/定时 revive。防止"一个卡住的 agent 无限烧钱"（headless 自动化的已知风险）。

## 密钥卫生

- `CURSOR_API_KEY` 只从环境变量读，**绝不**写入 config 文件或提交到 git。
- 证据/日志里对 key、token 脱敏。
- `config.example.yaml` 只放占位符与非敏感参数。

## 配置一览（config.example.yaml 字段）

```yaml
engine: local            # local | cloud(opt-in)
engines: [cursor_cli, opencode, codex]
repo_url: https://github.com/chuali-zi/agent_safety
starting_ref: auto-redteam/findings
model_id: <GET /v1/models 里选>
opencode_model_id: openai/gpt-5.6-sol
opencode_variant: high
codex_model_id: gpt-5.6-sol
codex_reasoning_effort: high
budget_usd: 20.0
per_objective_usd: 2.0
max_refines_per_objective: 3
run_timeout_s: 1800
max_agents: 20
max_runs: 100
breaker_max_errors: 3
objective_categories: [1,2,3,4,5,6]   # 7=多模态默认关闭
evidence_root: D:/xa-evidence/remote/local-auto-redteam
continuous: false
```
