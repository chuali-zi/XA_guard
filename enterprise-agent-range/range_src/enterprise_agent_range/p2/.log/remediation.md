# remediation.py 工作日志

2026-07-02：实现 P2 能力 6（Undo/补偿动作建议）真实逻辑，仅建议不执行。

- `RemediationPlanner.plan(side_effects, trace_id="")`：输入 side-effects.jsonl 风格 dict 列表，`committed` 为假的行直接跳过。
- 每条已提交效果生成一个 `CompensatingAction`：`action_id="undo-"+sha256(sink_type+":"+payload_hash)[:16]`（确定性，同输入同 id）；`target_side_effect_hash=payload_hash`。
- `description` 按 sink_type 映射：payment→submit reversal/hold request；email/mail→send retraction notice；plugin→quarantine and uninstall；http/egress→revoke/rotate exposed token；service→restore previous service state；notification→post correction notice；未知→manual review。
- `reversible`：payment/service/plugin/notification=True；email/mail/http/egress=False；未知 sink 保守默认 False。
- `actions` 按 `action_id` 排序，结果与输入顺序无关，保证确定性输出。
- `SPEC.status` 改为 `IMPLEMENTED`，仍只依赖 `.base` + stdlib（hashlib）。
- 测试见 `tests/test_p2_remediation.py`：每提交效果一动作、未提交忽略、可逆/不可逆标记、action_id 确定性、排序、空输入、类真实数据用例。
