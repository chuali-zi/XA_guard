# permissions.py 工作日志

2026-07-02：实现 P2 能力 4（JIT/JEA/JLA 权限签发）真实逻辑。

- `IssuedGrant.issued_at`/`expires_at` 改为 int epoch 秒，去除 ISO 字符串占位，保证确定性（无 `datetime.now()`/`time.time()`）。
- `GrantAuthority.issue(request, now_epoch: int)`：`grant_id` 为 `"grant-" + sha256(...)[:16]`，基于 request 全字段 + now_epoch 的稳定 JSON 序列化（`sort_keys=True`）计算，保证相同输入产生相同 grant_id；`expires_at = now_epoch + ttl_seconds`。
- `GrantAuthority.check(grant, capability, scope_needed, when_epoch)`：需同时满足未撤销（JIT）、`when_epoch < expires_at`（JLA）、capability 精确匹配、`scope_needed ⊆ request.scope`（JEA），任一不满足返回 False。
- 新增 `GrantAuthority.revoke(grant)`：返回撤销后的新对象，不改原对象。
- `SPEC.status` 改为 `CapabilityStatus.IMPLEMENTED`，仍只依赖 `.base` + stdlib（hashlib/json/dataclasses）。
- 测试见 `tests/test_p2_permissions.py`，覆盖确定性、过期/越权/错误能力/已撤销拒绝、合法通过。
