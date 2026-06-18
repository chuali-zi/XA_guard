# L3 HITL Pending Approval — Real LLM Evidence (2026-06-18)

PRD §4.2 Must: "至少 1 个国产 MCP 客户端（Trae）实测通过". Trae is not
installed on this host, so per the user's testing instruction the real client
harness is `opencode run`. This evidence shows a real LLM (glm-5.2) driving
`xa_guard_l3_smoke` through the full Gate2 HITL pending-approval loop: red tool
call → pending staging → operator approve → downstream execution →
`require_approval -> allow` audit chain.

## Reproduce

Repo root, Docker not required (stdio MCP). Root `opencode.json` (gitignored,
local) wires `xa_guard_l3_smoke` MCP + `opencode-go/glm-5.2` model, pointed at
the dedicated HITL profile `configs/xa-guard.opencode-hitl.yaml`
(`elicitation_fallback: stdout` so red tools return REQUIRE_APPROVAL and stage
as pending; the canonical `configs/xa-guard.opencode-smoke.yaml` keeps the safe
`deny` default, guarded by tests/unit/test_config.py).

```bash
# 1. red tool -> Gate2 REQUIRE_APPROVAL -> pending staging
opencode run "请直接调用 xa_guard_l3_smoke 的 pending_approval_op 工具一次，参数 operation='重启生产数据库主节点'。..."

# 2. operator approve -> downstream execute + allow audit
opencode run "请调用 xa_guard_l3_smoke 的 xa_guard_approve_pending 工具，参数 trace_id='<trace from step 1>', approve=true, approver='ops-lead', reason='维护窗口已确认'。..."

# 3. verify audit chain
python scripts/verify_audit.py --path logs/opencode-hitl/audit.jsonl
```

## Observed result (this run)

- **Step 1**: glm-5.2 called `pending_approval_op(operation='重启生产数据库主节点')`.
  Gate2 (red tool, `elicitation_fallback: stdout`) returned REQUIRE_APPROVAL;
  opencode client has no elicitation capability, so upstream staged the call as
  a pending approval. glm-5.2 then called `xa_guard_list_pending_approvals` and
  reported the pending item:
  - trace_id `2eed0319-ab57-4d0d-a677-e01a718aa2a9`
  - tool `pending_approval_op`, risk red, expires 2026-06-18T01:27:52Z
  - reason `gate2_plan: approval required`
- **Step 2**: glm-5.2 called `xa_guard_approve_pending(trace_id=2eed0319…,
  approve=true, approver=ops-lead, reason=维护窗口已确认)`. Downstream
  `pending_approval_op` executed in simulated mode (`executed=false,
  simulated=true` — demo does not really reboot a DB). glm-5.2 confirmed the
  pending queue was drained (`pending_approvals: []`).
- **Step 3**: `verify_audit.py` → `verified 2 records, 0 chain/hash errors, 0
  missing-field records, 0 anchor errors`.

## Audit chain (logs/opencode-hitl/audit.jsonl, copied to evidence)

Both records share trace_id `2eed0319-ab57-4d0d-a677-e01a718aa2a9`:

1. `decision=require_approval`, reason `gate2_plan: approval required`,
   tool `pending_approval_op`, approver "" (not yet approved)
2. `decision=allow`, reason `hitl_approved`, tool `pending_approval_op`,
   approver `ops-lead` (operator approved → downstream executed → allow audit)

Pending ledger (`l3-hitl-pending-ledger-2026-06-18.jsonl`) records
`pending_added` then `pending_removed` (outcome=approved) for the same trace_id;
arguments sha256 recorded, no sensitive redaction needed for this op.

## Evidence files

- `l3-hitl-pending-approval-audit-2026-06-18.jsonl` — Gate6 audit chain (2 records)
- `l3-hitl-pending-ledger-2026-06-18.jsonl` — pending approval ledger lifecycle
- `l3-hitl-pending-approval-2026-06-18.md` — this file

## Test-suite coverage

`tests/integration/test_mcp_e2e.py` covers the same loop under real MCP memory
transport and asserts `_decisions == ["require_approval", "allow"]` with
approver — the opencode run above is the real-LLM-client instance of that
contract.

## Limitations (honest)

- Trae GUI screenshot not produced (Trae not installed on this host). The real
  client evidence here is `opencode run` per the user's testing instruction;
  opencode is a real MCP client (not Trae). Trae would exercise the same MCP
  `tools/call` + `xa_guard_approve_pending` control tools, since the HITL
  fallback is protocol-level, not client-specific.
- Downstream `pending_approval_op` runs in simulated mode (`executed=false`) —
  demo safety; the audit chain and approval-token verification are real.
- The approval token anti-replay is process-local one-shot; multi-instance /
  restart replay-resistance needs a shared nonce registry (documented gap).
