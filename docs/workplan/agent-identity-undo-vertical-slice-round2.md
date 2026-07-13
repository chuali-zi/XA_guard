# Agent Identity + Undo 第二轮竖切执行说明

> 状态：**COMPLETED / ROUND2-GO / NOT PRODUCTIZED**
> 设计依据：[`agent-identity-undo-feasibility-round2.md`](../planning/agent-identity-undo-feasibility-round2.md)

## 1. 执行命令

```powershell
$env:PYTHONPATH='src;open-agent-range;.'
python open-agent-range/experiments/agent_identity_undo/round2.py `
  --out docs/evidence/agent-identity-undo-spike-round2-2026-07-12

python -m pytest open-agent-range/experiments/agent_identity_undo/test_round2.py -q
```

## 2. 固定步骤

1. 生成进程内 Ed25519 issuer、Alice/Carol Bearer token 和 AES-256-GCM 恢复密钥。
2. 构建真实 XA-Guard Streamable HTTP ASGI app，以实验 Bearer middleware 包裹，不修改正式 upstream。
3. 验证缺 token、坏签名、身份冲突、tool scope 越权的 HTTP 401/403 和 executor 零调用。
4. Alice 通过真实 MCP ClientSession 调用 `update_registry`，保存原 trace 与前后态 hash。
5. 将最小恢复材料加密写入 SQLite，关闭并重新创建 EffectStore。
6. 用正确密钥恢复；用错误密钥验证 AES-GCM fail closed；扫描 SQLite 原始字节确认无前态明文。
7. 同一幂等键申请两次 Undo，断言 request ID 相同；Alice 自批拒绝。
8. 两个独立 store 实例并发 claim，断言恰好一个成功。
9. Carol 通过新的 Bearer MCP session 执行补偿，恢复前态并完成 EffectRecord。
10. 再次打开 store，验证状态持久化；封存 audit、ledger、数据库、事件导出、HTTP 负测、世界快照和 hash manifest。

## 3. 证据与验收

第二轮 evidence 至少包含：

- `summary.json`、`http-negative-cases.json`
- `audit.jsonl`、`ledger.jsonl`
- `effects.sqlite3`、`effect-events.jsonl`
- `world-before.json`、`world-after-action.json`、`world-after-undo.json`
- `commands.txt`、`environment.json`、`README.md`、`artifact-hashes.json`

私钥、AES key、完整 Bearer token 不得进入任何 evidence；恢复前态只允许出现在明确的合成世界快照中，
不得以明文进入 SQLite、audit 或 ledger。测试失败时保留真实 `NO-GO` 诊断，但不得把失败包冒充最终证据。

实际结果：2026-07-12 第二轮所有条件成立，结论为 `ROUND2-GO`。该结论不自动触发正式产品改造。

## 4. 不做

- 不修改既有测试断言。
- 不改正式 XA-Guard 源码、配置和 schema。
- 不覆盖第一轮或 canonical OAR evidence。
- 不把本轮本地 SQLite/AES-GCM PoC 宣传成生产级恢复服务。
