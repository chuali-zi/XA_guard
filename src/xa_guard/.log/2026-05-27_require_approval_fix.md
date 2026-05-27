2026-05-27 REQUIRE_APPROVAL short-circuit fix

pipeline.py: inbound gate loop now short-circuits on REQUIRE_APPROVAL same as DENY — gate6 audit runs, executor skipped, PipelineResult(allowed=False, final_decision=REQUIRE_APPROVAL). Updated module docstring.

test_pipeline_smoke.py: added _ApprovalGate, _AuditStubGate stubs and test_pipeline_blocks_executor_on_require_approval. All 3 smoke tests pass.
