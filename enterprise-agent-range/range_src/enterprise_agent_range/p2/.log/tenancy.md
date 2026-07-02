# tenancy.py 工作日志

2026-07-02：将 `TenantRegistry` 从纯桩实现为确定性逻辑。

- `register(tenant)`：按 `tenant_id` 存储，重复注册抛 `ValueError`。
- `get(tenant_id)`：查不到抛 `KeyError`。
- `list_tenants()`：按 `tenant_id` 排序返回，保证确定性输出。
- `isolate(tenant_id, rows)`：对 dict 行列表按 `tenant_id` 过滤，仅返回属于该租户的行，保序（静态方法，纯函数）。
- `cross_tenant_violations(tenant_id, rows)`：返回 `tenant_id` 不匹配或缺失的行，用于跨租户泄露检测。
- `SPEC.status` 置为 `CapabilityStatus.IMPLEMENTED`。

未改动 `base.py`/`registry.py`/`schema.py` 等公共文件，未 import xa_guard 或其他 P2 能力模块。新增测试 `tests/test_p2_tenancy.py` 覆盖 register/get/list/isolate/cross_tenant_violations 的正常与边界场景。
