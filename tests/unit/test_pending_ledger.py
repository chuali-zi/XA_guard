from __future__ import annotations

from xa_guard.proxy.pending import PendingApprovalStore, arguments_are_redacted, redact_arguments
from xa_guard.types import Decision, GateContext, GateResult, RiskLevel, TaintLabel


def _ctx() -> GateContext:
    ctx = GateContext(
        tool_name="exec_command",
        arguments={"cmd": "whoami"},
        input_sources=[],
    )
    ctx.final_decision = Decision.REQUIRE_APPROVAL
    ctx.final_reason = "gate2_plan: approval required"
    ctx.risk_level = RiskLevel.RED
    ctx.taint = TaintLabel.INTERNAL
    ctx.rule_hits = ["GBT-22239-8.1.4.4"]
    ctx.gate_results = [
        GateResult(
            gate_name="gate2_plan",
            decision=Decision.REQUIRE_APPROVAL,
            rule_hits=["GBT-22239-8.1.4.4"],
            metadata={"approval_token": "must-not-persist", "risk_level": "red"},
        )
    ]
    return ctx


def test_pending_ledger_restores_context_without_approval_token(tmp_path):
    ledger = tmp_path / "pending.jsonl"
    store = PendingApprovalStore(ledger_path=ledger)
    item = store.add(_ctx())

    restored = PendingApprovalStore(ledger_path=ledger)
    listed = restored.list()

    assert len(listed) == 1
    assert listed[0].ctx.trace_id == item.ctx.trace_id
    assert listed[0].ctx.final_decision == Decision.REQUIRE_APPROVAL
    assert listed[0].ctx.final_reason == "gate2_plan: approval required"
    assert listed[0].ctx.risk_level == RiskLevel.RED
    assert listed[0].ctx.taint == TaintLabel.INTERNAL
    assert listed[0].ctx.rule_hits == ["GBT-22239-8.1.4.4"]
    assert listed[0].ctx.gate_results[0].metadata == {"risk_level": "red"}
    text = ledger.read_text(encoding="utf-8")
    assert "approval_token" not in text
    assert "must-not-persist" not in text


def test_pending_ledger_redacts_sensitive_arguments_before_write(tmp_path):
    ledger = tmp_path / "pending.jsonl"
    ctx = _ctx()
    ctx.arguments = {
        "cmd": "deploy",
        "password": "p@ssw0rd",
        "headers": {
            "Authorization": "Bearer secret-token",
            "X-Request-Id": "req-1",
        },
        "items": [{"api_key": "abc123"}],
        "monkey": "banana",
    }

    PendingApprovalStore(ledger_path=ledger).add(ctx)
    restored = PendingApprovalStore(ledger_path=ledger).list()[0].ctx
    text = ledger.read_text(encoding="utf-8")

    assert restored.arguments["cmd"] == "deploy"
    assert restored.arguments["password"].startswith("[REDACTED]:sha256:")
    assert restored.arguments["headers"]["Authorization"].startswith("[REDACTED]:sha256:")
    assert restored.arguments["headers"]["X-Request-Id"] == "req-1"
    assert restored.arguments["items"][0]["api_key"].startswith("[REDACTED]:sha256:")
    assert restored.arguments["monkey"] == "banana"
    assert arguments_are_redacted(restored.arguments)
    assert "p@ssw0rd" not in text
    assert "Bearer secret-token" not in text
    assert "abc123" not in text


def test_pending_ledger_redaction_is_recursive_but_keeps_non_sensitive_values():
    safe = redact_arguments(
        {
            "path": "/var/log/app.log",
            "nested": [{"cookie": "session-id"}, {"host": "server-1"}],
            "monkey": "banana",
        }
    )

    assert safe["path"] == "/var/log/app.log"
    assert safe["nested"][0]["cookie"].startswith("[REDACTED]:sha256:")
    assert safe["nested"][1]["host"] == "server-1"
    assert safe["monkey"] == "banana"


def test_pending_ledger_uses_input_schema_sensitive_annotations(tmp_path):
    ledger = tmp_path / "pending.jsonl"
    ctx = _ctx()
    ctx.arguments = {
        "tenant": "finance-bureau",
        "public_note": "ok",
        "items": [
            {"label": "first", "code": "C-001"},
            {"label": "second", "code": "C-002"},
        ],
    }
    schema = {
        "type": "object",
        "properties": {
            "tenant": {"type": "string", "x-xa-guard-sensitive": True},
            "public_note": {"type": "string"},
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "code": {"type": "string", "writeOnly": True},
                    },
                },
            },
        },
    }

    PendingApprovalStore(ledger_path=ledger).add(ctx, input_schema=schema)
    restored = PendingApprovalStore(ledger_path=ledger).list()[0].ctx
    text = ledger.read_text(encoding="utf-8")

    assert restored.arguments["tenant"].startswith("[REDACTED]:sha256:")
    assert restored.arguments["public_note"] == "ok"
    assert restored.arguments["items"][0]["label"] == "first"
    assert restored.arguments["items"][0]["code"].startswith("[REDACTED]:sha256:")
    assert "finance-bureau" not in text
    assert "C-001" not in text
    assert "C-002" not in text


def test_pending_ledger_pop_records_lifecycle_and_prevents_replay(tmp_path):
    ledger = tmp_path / "pending.jsonl"
    store = PendingApprovalStore(ledger_path=ledger)
    item = store.add(_ctx())

    popped = store.pop(item.ctx.trace_id, outcome="approved")
    replay = PendingApprovalStore(ledger_path=ledger).pop(item.ctx.trace_id)

    assert popped is not None
    assert replay is None
    events = ledger.read_text(encoding="utf-8").splitlines()
    assert any('"event": "pending_added"' in line for line in events)
    assert any('"event": "pending_removed"' in line and '"outcome": "approved"' in line for line in events)


def test_pending_ledger_prunes_expired_items(tmp_path):
    ledger = tmp_path / "pending.jsonl"
    store = PendingApprovalStore(ledger_path=ledger, ttl_seconds=-1)
    item = store.add(_ctx())

    assert store.list() == []
    assert PendingApprovalStore(ledger_path=ledger).pop(item.ctx.trace_id) is None
    assert '"outcome": "expired"' in ledger.read_text(encoding="utf-8")
