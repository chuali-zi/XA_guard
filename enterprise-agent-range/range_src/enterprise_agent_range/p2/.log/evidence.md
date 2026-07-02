# evidence.py 工作日志

2026-07-02：将 `TimestampAuthority`/`HsmSigner` 从纯桩实现为确定性离线 mock 逻辑。

- `TimestampAuthority.stamp(evidence_hash, at)`：用 `hmac.new(_MOCK_TSA_KEY, f"{evidence_hash}|{at}", sha256)` 生成 `token_ref`，返回 `TimestampToken`。
- `TimestampAuthority.verify(token)`：重算 HMAC 并用 `hmac.compare_digest` 常量时间比较；篡改 `evidence_hash`/`timestamp`/`token_ref` 任一字段均返回 `False`。
- `HsmSigner.sign(payload)`：返回 `{"algo","key_id","signature"}`，签名为 `hmac.new(_MOCK_HSM_KEY, payload, sha256)` 十六进制摘要，同输入确定性输出。
- `HsmSigner.verify(payload, signature)`：重算并常量时间比较。
- 仅用 `_MOCK_TSA_KEY = b"range-mock-tsa-key"` / `_MOCK_HSM_KEY = b"range-mock-hsm-key"`，明确注释为非生产 mock，不接触真实 TSA/HSM。
- `SPEC.status` 置为 `CapabilityStatus.IMPLEMENTED`。

仅依赖 stdlib（hashlib/hmac），未改动 `base.py`/`registry.py`，未 import xa_guard 或其他 P2 模块。新增 `tests/test_p2_evidence.py` 覆盖 stamp→verify 往返、三种篡改场景、签名确定性/篡改检测、mock key 常量校验。
