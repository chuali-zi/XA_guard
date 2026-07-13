from __future__ import annotations

import base64
import asyncio
import json

import mcp.types as mtypes
import pytest

from xa_guard.config import ResilienceConfig
from xa_guard.identity import VerifiedIdentity
from xa_guard.resilience import ResilienceError, ResilienceManager
from xa_guard.types import Decision, GateContext


def _manager(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_RECOVERY_KEY", base64.b64encode(b"k" * 32).decode())
    contracts = tmp_path / "contracts.yaml"
    contracts.write_text("""
tools:
  create_item:
    side_effect_level: high
    reversibility: compensatable
    recovery_fields: {item_id: '$result#/body/item_id'}
    undo_tool: delete_item
    undo_arguments: {item_id: '$recovery#/item_id', reason: '$request#/reason'}
""", encoding="utf-8")
    return ResilienceManager(ResilienceConfig(True, str(contracts), str(tmp_path / "effects.db"), "TEST_RECOVERY_KEY"))


def _identity(name, permission):
    return VerifiedIdentity(name, "agent", "tenant", "issuer", ("xa.invoke",), ("create_item", "delete_item"), ("domain",), (permission,), "kid", "jti-hash")


def test_effect_is_encrypted_idempotent_and_separation_of_duty_is_enforced(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch)
    ctx = GateContext(tool_name="create_item", arguments={"name": "TOP-SECRET-NAME"}, tenant_id="tenant", human_principal="alice", agent_id="agent", data_domain="domain")

    async def execute(_ctx):
        return mtypes.CallToolResult(content=[mtypes.TextContent(type="text", text=json.dumps({"ok": True, "body": {"item_id": "secret-item-17"}}))])

    asyncio.run(manager.execute(ctx, execute))
    database = (tmp_path / "effects.db").read_bytes()
    assert b"secret-item-17" not in database and b"TOP-SECRET-NAME" not in database
    first = manager.request_undo(_identity("alice", "undo.request"), {"effect_id": ctx.effect_id, "reason": "mistake", "idempotency_key": "same-key"})
    second = manager.request_undo(_identity("alice", "undo.request"), {"effect_id": ctx.effect_id, "reason": "mistake", "idempotency_key": "same-key"})
    assert first["request_id"] == second["request_id"] and second["created"] is False
    with pytest.raises(ResilienceError, match="self-approval"):
        manager.store.claim(first["request_id"], "alice", "tenant")


def test_approved_compensation_runs_through_pipeline_with_recovery_id(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch)
    forward = GateContext(tool_name="create_item", arguments={}, tenant_id="tenant", human_principal="alice", agent_id="agent", data_domain="domain")
    async def create(_ctx):
        return {"ok": True, "body": {"item_id": "item-42"}}
    asyncio.run(manager.execute(forward, create))
    req = manager.request_undo(_identity("alice", "undo.request"), {"effect_id": forward.effect_id, "reason": "rollback", "idempotency_key": "request-42"})
    seen = []
    class Pipeline:
        async def run(self, ctx, executor):
            seen.append(ctx)
            ctx.tool_result = await executor(ctx)
            ctx.final_decision = Decision.ALLOW
            return type("Result", (), {"allowed": True, "final_decision": Decision.ALLOW})()
    async def compensate(ctx):
        return {"ok": True, "deleted": ctx.arguments["item_id"]}
    result = asyncio.run(manager.approve_undo(_identity("bob", "undo.approve"), {"request_id": req["request_id"], "reason": "approved"}, Pipeline(), compensate))
    assert result["status"] == "compensated"
    assert seen[0].tool_name == "delete_item" and seen[0].arguments["item_id"] == "item-42"
    assert seen[0].operation_kind == "compensation" and seen[0].compensates_effect_id == forward.effect_id
