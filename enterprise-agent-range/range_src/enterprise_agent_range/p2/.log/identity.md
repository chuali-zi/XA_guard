# identity.py 工作日志

2026-07-02：实现 P2 能力 3（Agent 身份生命周期）真实逻辑。

- `IdentityState` 六态：provisioned/active/rotated/suspended/revoked/retired。
- `ALLOWED_TRANSITIONS` 显式转移表：provisioned→active；active/rotated 可互转并可 suspend/revoke/retire；suspended 可 active/revoke/retire；revoked 只能 retire；retired 终态无出边。
- `IdentityLifecycle.transition(identity, to_state)`：非法目标态或非法转移抛 `ValueError`；返回新的 frozen `AgentIdentity`；转到 rotated 时用 `_rotate_credential_ref` 确定性追加/递增 `-rN` 后缀（纯字符串解析，无随机/时间）。
- `IdentityLifecycle.can_act(identity)`：仅 active/rotated 返回 True，作为安全关键闸门。
- 新增 `IdentityRegistry`（register/get/list）便于集成测试。
- `SPEC.status` 改为 `CapabilityStatus.IMPLEMENTED`，字段/依赖不变，仍只依赖 `.base` + stdlib。
- 测试见 `tests/test_p2_identity.py`，覆盖合法/非法转移、can_act 边界、rotate 确定性、registry。
