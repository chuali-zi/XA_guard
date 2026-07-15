# Agent Identity + Undo reference verification（未封存）

状态：`PARTIAL EVIDENCE / NOT REFERENCE-READY`

本目录记录 2026-07-12（America/Los_Angeles；容器日志为 2026-07-13 UTC）的实际 reference 验证。它不包含密码、JWT、client secret、KEK、DSN、recovery 明文或完整 effect/ticket 标识。

## 已实际完成

```powershell
python scripts/reference_stack.py up
curl http://127.0.0.1:13000/readyz
python scripts/verify_reference_e2e.py
```

`readyz`：

```json
{"status":"ready","checks":{"postgresql":true,"oidc_jwks":true}}
```

协议验收输出：

```json
{"alice_self_approval_rejected":true,"alice_subject_verified":true,"dora_independent_approval":true,"effect_status":"compensated","flow":"authorization_code_pkce -> token_exchange -> effect -> independent_approval -> worker_compensation","separate_traces":true,"status":"passed","tokens_persisted_or_printed":false,"undo_idempotency_verified":true}
```

PostgreSQL 将最新 Effect 与参考工单关联后得到：

```text
compensated:cancelled:true
```

三项分别表示 Effect 已补偿、业务工单已从 `open` 恢复为 `cancelled`、原动作 trace 与补偿 trace 不同。服务日志还显示 Alice self-decision 为 403，Dora decision 为 200，Worker 对 cancel API 的调用为 200。

构建/测试：

- Python reference 镜像从锁定 digest 的 Python 3.12.11 slim 构建成功。
- Keycloak 26.7.0 与 PostgreSQL 17.6 均使用锁定 digest；migration schema version 为 3。
- seed 后 `jsonb_typeof(tools)` / `jsonb_typeof(data_domains)` 均为 `array`。
- Control/identity/intent/deployment 目标集合：18 passed；可靠性回归集合：18 passed。
- Console：5 tests passed，Vite production build passed，npm audit 0 vulnerabilities。
- 无 Bearer 的 `/control/v1/me` 返回安全 401，响应 header/body 使用同一个 trace ID，且下游未执行。
- 最终 CI 口径 Ruff PASS；全仓 pytest 691 collected / 691 passed / 0 failed / 0 skipped；`git diff --check` PASS。

## 尚未完成，因此不能封存 B6/B7

- 当前环境没有可用的交互式浏览器控制实例；三账号 UI 视觉验收、截图和录屏未完成。协议测试使用真实 Authorization Code + PKCE，不使用 direct grant。
- 2026-07-15 已在全新 volume 上完成 core suite：坏签名/错误 audience/伪造身份零下游、assignment 撤销、跨租户、PostgreSQL 断连零下游、API crash-window reconciliation 和双审批单任务 7/7 通过；本目录尚未纳入并封存该运行。
- Worker kill/lease takeover、5/30/120 retry、错误 KEK/rewrap 的整栈故障注入仍未封存。
- 10 并发 identity/effect p95 与批准到恢复时延的正式统计未完成。
- kind 双 API/双 Worker、NetworkPolicy、外部 IdP/PostgreSQL/key provider 替换和 Helm rollback 未验收。
- 本目录还不是最终 artifact manifest；不得据此把 Delivery v2 B6/B7 改为 `DONE`。

最终封存应在全新 runtime 上重跑，保存脱敏身份 claims 摘要、assignment 版本、Effect/Undo 事件、业务前后态、两条 trace、Gate6/Effect chain 校验与 SHA-256 artifact manifest。
