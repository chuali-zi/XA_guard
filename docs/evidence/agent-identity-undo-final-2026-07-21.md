# Identity + Undo 最终候选证据（2026-07-21）

## 结论

最终候选 evidence 已从干净源码提交 `610de9262fa541ee9202ad82693daf4795fde3f6` 采集、以 SM2-with-SM3 封存并独立验签通过。

| 项 | 结果 |
|---|---|
| bundle | `docs/evidence/agent-identity-undo-final-2026-07-21/` |
| run id | `reference-identity-undo-eff-4dec20b128244c498187bbd1a83a3c9f` |
| artifact | 14 |
| Effect records | 102 |
| Gate6 records | 59 |
| signature | SM2-with-SM3 |
| public key id | `87ca0b5c56dc9313` |
| manifest SHA-256 | `9950382f73a64b725333e37b7377cdb6b208f12b26ba207df5a122c720010415` |
| sealing metadata SHA-256 | `9de9af6a3bea851d6365f47b5a0f3edc39104b2fa3bae8e6bb2edb049ada68e0` |

## 随包验收报告

- Reference 最终 all fault：11/11 PASS；报告 SHA-256 `089ede1cc61937b15fa1221463b276cc8b41345039d6209dbca68f8eba3f96fe`。
- 本地三节点 kind HA：安装、升级、迁移重跑、API/Worker 接管、NetworkPolicy 与回滚全阶段 PASS；报告 SHA-256 `b5ae417eb9bd3509eb03bca91c33232f942c46d887df056feaab94942b34180c`。
- 完整重建镜像正式性能：三轮 p95/upper 均 ≤50ms，Undo 10/10；报告 SHA-256 `6c0fac3d635ce21435b52115e644a95b487563e9023c663c256b6a642177e65b`。

## 独立验证

```powershell
python scripts/verify_identity_undo_evidence.py `
  --bundle docs/evidence/agent-identity-undo-final-2026-07-21 `
  --expected-key-id 87ca0b5c56dc9313
```

成功标准：退出码 0，`ok=true`，artifact 14、Effect 102、Gate6 59，签名算法与 key id 和上表一致。

## 声明边界

- bundle 证明一个 Reference Compose 的身份、职责分离、真实副作用恢复和双链交叉引用流程，并绑定三份最终候选验收报告。
- 补偿语义是至少一次调度配合下游幂等，不宣称绝对 exactly-once。
- Gate6 是链校验后的公开投影，排除了可重放凭据；私钥位于 gitignored 运行目录且未进入 bundle。
- kind 报告只证明本机三节点 profile，不外推为生产多地域 HA。
