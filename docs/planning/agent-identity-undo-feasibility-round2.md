# Agent Identity 与 Undo 第二轮可行性设计

> 状态：**ROUND2-GO / NOT DELIVERED**
> 日期：2026-07-12
> 前置结论：[`agent-identity-undo-feasibility.md`](./agent-identity-undo-feasibility.md) 第一轮为 `FEASIBILITY GO`。

## 1. 第二轮要回答的问题

第一轮证明了签名双主体身份可以在 Pipeline 前 fail closed，也证明了 OAR 合成状态可以通过第二主体补偿恢复；但签名器和恢复材料都只存在于实验进程内。

第二轮只验证两个新增风险：

1. **真实 MCP 传输边界**：Bearer 凭据能否在 Streamable HTTP 请求进入 XA-Guard 前完成验签，并把签名人类/Agent 与 `tools/call` 的 `_xa_guard` envelope 绑定。
2. **跨实例恢复**：EffectRecord 和最小前态能否加密写入 SQLite，在重新创建 store 后恢复，并保持幂等、职责分离和并发单次执行。

第二轮仍是隔离实验，不修改 `src/xa_guard`、默认配置、正式 Governance schema 或比赛交付口径。

## 2. HTTP 身份边界

实验使用 MCP SDK 的 `TokenVerifier`、Bearer authentication middleware 和 `AccessToken` 模型：

- 每个 HTTP 请求必须携带 `Authorization: Bearer <compact-JWS>`。
- TokenVerifier 校验 Ed25519 签名、issuer、audience、`iat/nbf/exp`、五分钟 TTL、人类 `sub` 和 Agent `act.sub`。
- `tools/call` 进入 XA-Guard 前，实验 middleware 比对 token claims 与请求中的 tenant、principal、agent、data domain 和 tool。
- 请求 envelope 只能与签名 claims 相等或进一步缩小范围，不能覆盖签名主体。
- 验签成功后，正式 upstream 仍按原路径剥离 `_xa_guard`，下游 OAR 工具看不到 Bearer token 或治理 envelope。

第二轮不实现 OAuth authorization server、登录/同意页、远程 JWKS discovery、PKCE 或生产 token exchange；只验证 XA-Guard 作为受保护 resource server 的最小入口可行性。

## 3. 加密 EffectStore

SQLite 只保存控制状态和密文：

- `effects`：effect ID、tenant、原 trace、主体、Agent、工具、可逆性、前后态 hash、状态、nonce、ciphertext、key ID 和补偿 trace。
- `undo_requests`：request ID、effect ID、幂等键、requester、状态和 approver；幂等键全局唯一。
- `events`：append-only 生命周期事件，使用 `prev_hash + canonical event` 形成独立 hash chain。

恢复材料使用 AES-256-GCM：

- 256 位密钥只由调用方注入，数据库不保存密钥。
- AAD 绑定 `effect_id / tenant_id / tool_name / schema_version`。
- 数据库只保存 nonce、ciphertext、key ID 和明文 hash；错误密钥或篡改必须 fail closed。
- 前态只保存恢复需要的最小字段，本轮为合成 registry entry。

## 4. 状态机与并发

固定状态流：

```text
available -> undo_pending -> compensating -> compensated
                               \-> compensation_failed
```

- 相同 `idempotency_key` 重复申请必须返回同一 request ID，且只追加一次 `undo_requested` 事件。
- 原动作主体不得批准自己的 Undo。
- 两个独立 SQLite store 实例并发 claim 同一请求时，只能一个成功进入 `compensating`。
- claim 成功后，补偿动作通过 Carol 的独立 Bearer token 再次调用真实 XA-Guard Streamable HTTP Pipeline。
- 补偿完成后重新打开 store，必须读到 `compensated` 和补偿 trace。

## 5. 第二轮通过条件

- HTTP 缺 token、坏签名返回 401；身份冲突和 tool scope 越权返回 403；四类拒绝均不触发下游。
- 合法 Alice Bearer 调用真实 Streamable HTTP `update_registry` 成功。
- SQLite 文件中不存在恢复前态明文、完整 token 或密钥。
- 正确密钥跨 store 实例恢复前态；错误密钥解密失败。
- 重复 Undo 返回同一 request；Alice 自批失败；并发 claim 恰好一个成功。
- Carol 补偿经真实 HTTP/Pipeline 执行，世界状态恢复，重新打开 store 后状态仍为 `compensated`。
- XA-Guard Gate6 audit、OAR ledger、EffectStore event chain 和 artifact manifest 全部通过。

全部成立为 `ROUND2-GO`。任何身份拒绝触发下游、密文可见明文、并发双执行或错误密钥可解密均为 `NO-GO`。

## 6. 仍未覆盖

- 生产 IdP、OIDC discovery、JWKS 轮换、token revocation 和 SPIFFE attestation。
- 正式 XA-Guard HTTP middleware 接入和正式 MCP control tools。
- 多进程/多主机数据库、KMS/HSM、密钥轮换和生产备份。
- 补偿失败重试调度、真实工单/支付/邮件连接器和通用 Saga DSL。

## 7. 2026-07-12 实验结果

第二轮结论为 **ROUND2-GO**，证据见
[`docs/evidence/agent-identity-undo-spike-round2-2026-07-12/`](../evidence/agent-identity-undo-spike-round2-2026-07-12/)：

- 缺 Bearer、坏签名分别返回 401；签名身份与 envelope 冲突、tool scope 越权分别返回 403；四类负测的 executor 调用为 0。
- Alice 通过真实 Streamable HTTP MCP session 执行 `update_registry`，Carol 通过独立 Bearer session 执行补偿。
- AES-GCM 恢复材料在重新创建 EffectStore 后可解密，错误密钥 fail closed，SQLite 原始字节不含合成前态明文。
- 重复幂等请求返回同一 request ID；Alice 自批拒绝；两个独立 store 并发 claim 时只有一个进入 `compensating`。
- 补偿后世界状态恢复，第三次打开 store 仍为 `compensated`；Gate6 audit、OAR ledger、EffectStore event chain 全部通过。
- 第二轮 3 项测试连续 3 轮通过；第一轮 3 项兼容测试和相关基线 51 项通过；Ruff 与 diff check 通过。
- evidence 共 12 项稳定 artifact，manifest 复验无缺失、无 hash mismatch；SQLite `-wal/-shm` 临时文件明确不进入 manifest。

首次第二轮测试曾因 ASGI middleware 重放 request body 后没有把后续 `receive()` 交还原通道而挂起；修复后 MCP session 可正常关闭。
首次 evidence manifest 曾误收 SQLite 临时 `-shm` 文件，进程结束后复验缺失；现只封存 checkpoint 后的主数据库与稳定工件。

该 GO 仍只表示真实 HTTP 和本地加密恢复路径具备工程可行性，不代表生产部署完成。
