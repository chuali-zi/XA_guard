# Agent Identity + Undo 最小竖切执行说明

> 状态：**COMPLETED / FEASIBILITY GO / NOT PRODUCTIZED**
> 设计依据：[`docs/planning/agent-identity-undo-feasibility.md`](../planning/agent-identity-undo-feasibility.md)

## 1. 固定实验路径

实验代码位于 `open-agent-range/experiments/agent_identity_undo/`，调用真实 XA-Guard Pipeline，并以 OAR `World / ToolSurface / Ledger` 作为合成下游。

执行命令：

```powershell
$env:PYTHONPATH='src;open-agent-range;.'
python open-agent-range/experiments/agent_identity_undo/vertical_slice.py `
  --out docs/evidence/agent-identity-undo-spike-2026-07-12

python -m pytest open-agent-range/experiments/agent_identity_undo/test_vertical_slice.py -q
```

相关回归：

```powershell
$env:PYTHONPATH='src;.'
python -m pytest `
  tests/unit/test_governance.py `
  tests/unit/test_governance_enterprise.py `
  tests/integration/test_governance_mcp.py `
  tests/integration/test_streamable_http_e2e.py `
  tests/unit/test_pending_ledger.py `
  tests/test_approval.py `
  open-agent-range/kernel/tests/test_smoke.py -q
```

## 2. 实验步骤

1. 建立仅用于实验的 tenant、Alice 操作员、Carol 安全审批员、`open-agent-range` Agent registry，
   并为两个实验工具提供本地可信 capability 声明；未登记工具仍沿用 Gate4 fail-closed 行为。
2. 进程内生成 Ed25519 密钥，为 Alice/Carol 签发五分钟内有效的双主体 compact JWS。
3. 对 `update_registry` 执行四个身份负测：坏签名、过期、错误 audience、自报 principal 与签名 principal 冲突。
4. 断言四个负测均由 Pipeline 写 Gate6 deny 审计，OAR executor 调用次数保持零。
5. 使用 Alice 合法凭据执行 `update_registry`，在执行前保存目标 entry 和 hash，执行后生成 EffectRecord。
6. Alice 发起 Undo；Alice 自批被职责分离规则拒绝；Carol 使用带 `undo.approve` 的合法凭据批准。
7. Carol 的补偿调用再次经过同一 Pipeline，恢复原 registry entry，并产生独立 trace 和 OAR ledger 事实。
8. 使用 Alice 执行合成 `send_message`，将 EffectRecord 标记为 `irreversible`；Undo 请求只返回 `manual_required`。
9. 校验 audit chain、ledger chain、状态恢复、trace 分离和敏感凭据不落盘，生成 hash manifest。

## 3. 证据契约

实验目录至少包含：

- `summary.json`：Go/No-Go 判据与布尔结果。
- `audit.jsonl`：真实 Gate6 审计。
- `ledger.jsonl`：OAR 原动作、effect、补偿与不可逆事实。
- `effect-events.jsonl`：最小 EffectRecord 生命周期。
- `world-before.json`、`world-after-action.json`、`world-after-undo.json`。
- `environment.json`、`commands.txt`、`README.md`、`artifact-hashes.json`。

不得包含私钥、完整 JWS、未摘要 jti 或真实业务数据。

## 4. 通过条件

- `identity_denied_executor_count == 0`
- `valid_identity_action_executed == true`
- `state_restored == true`
- `self_approval_denied == true`
- `compensation_trace_distinct == true`
- `audit_chain_ok == true`
- `ledger_chain_ok == true`
- `raw_token_absent == true`
- `irreversible_truthful == true`

全部成立时结论为 `GO`。任一核心安全条件失败时不得写 GO，也不得继续正式工程化。

实际结果：2026-07-12 evidence 的九项条件全部满足，结论为 `GO`。该结论仅授权进入后续工程评审，
不会自动把提案写入正式产品、默认配置或比赛交付承诺。

## 5. 明确不做

- 不修改已有测试断言或跳过测试。
- 不修改默认 XA-Guard 配置与正式 Governance schema。
- 不覆盖已有 OAR canonical evidence。
- 不实现或宣称生产级 JWT/OIDC、IAM、加密恢复库、并发 Saga 或通用 Undo。
