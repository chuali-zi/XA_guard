# 2026-05-27 fix: audit record carries final_decision

Added `gen_ai_decision_final` / `gen_ai_decision_final_reason` to `AuditRecord` (types.py) and their OTel keys in `to_dict()`. Populated from `ctx.final_decision.value` / `ctx.final_reason` in `Gate6Audit.evaluate()`. New test `test_audit_record_carries_final_decision` verifies DENY propagation. All 9 tests pass.
