from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from xa_guard.control.ceiling import GovernanceCeiling
from xa_guard.control.contracts import ContractRegistry
from xa_guard.control.crypto import InternalAuthorization
from xa_guard.control.models import Principal
from xa_guard.control.service import ControlService
from xa_guard.control.store import ConflictError
from xa_guard.types import Decision


class PassPipeline:
    async def run(self, ctx, executor):
        value = await executor(ctx)
        ctx.tool_result = value
        return SimpleNamespace(allowed=True, final_decision=Decision.ALLOW, tool_result=value)


class FailingPrepareStore:
    async def authorize(self, *_args):
        return {"version": 1}

    async def prepare_effect(self, **_kwargs):
        raise RuntimeError("postgres unavailable")


class CountingBusiness:
    def __init__(self) -> None:
        self.calls = 0

    async def create_ticket(self, **_kwargs):
        self.calls += 1
        return {"ok": True, "body": {"ticket_id": "TKT-1"}}


def test_postgres_prepare_failure_prevents_any_downstream_call() -> None:
    store = FailingPrepareStore()
    business = CountingBusiness()
    service = ControlService(
        store=store,
        business=business,
        pipeline=PassPipeline(),
        contracts=ContractRegistry("policies/baseline/tool_effects.yaml", "policies/baseline/gate4_capabilities.yaml"),
        ceiling=GovernanceCeiling("configs/governance.enterprise-static.yaml"),
        internal_authorization=InternalAuthorization(b"k" * 32),
    )
    principal = Principal(
        subject="alice-sub",
        username="alice",
        tenant_id="acme-corp",
        agent_id="general-office-agent",
        issuer="test",
        token_id_hash="hash",
    )
    with pytest.raises(RuntimeError, match="postgres unavailable"):
        asyncio.run(
            service.create_ticket(
                principal,
                {"title": "wrong ticket", "description": "must be undone", "priority": "normal"},
            )
        )
    assert business.calls == 0


def test_caller_cannot_override_signed_tenant_in_ticket_body() -> None:
    store = FailingPrepareStore()
    business = CountingBusiness()
    service = ControlService(
        store=store,
        business=business,
        pipeline=PassPipeline(),
        contracts=ContractRegistry("policies/baseline/tool_effects.yaml", "policies/baseline/gate4_capabilities.yaml"),
        ceiling=GovernanceCeiling("configs/governance.enterprise-static.yaml"),
        internal_authorization=InternalAuthorization(b"k" * 32),
    )
    principal = Principal("alice-sub", "alice", "acme-corp", "general-office-agent", "test", "hash")
    with pytest.raises(ConflictError):
        asyncio.run(
            service.create_ticket(
                principal,
                {"tenant_id": "beta-corp", "title": "x", "description": "y"},
            )
        )
    assert business.calls == 0
