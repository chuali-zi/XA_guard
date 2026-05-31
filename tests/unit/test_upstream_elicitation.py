"""Unit tests for upstream HITL elicitation helpers."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from mcp import types as mtypes

from xa_guard.proxy import upstream
from xa_guard.proxy.upstream import _build_app, _client_supports_elicitation, _request_hitl_approval
from xa_guard.pipeline import PipelineResult
from xa_guard.types import Decision
from xa_guard.types import GateContext


class _FakeSession:
    def __init__(self, *, client_params=None, result=None):
        self.client_params = client_params
        self.result = result
        self.calls = []

    async def elicit_form(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


class _FakeApp:
    def __init__(self, request_context):
        self._request_context = request_context

    @property
    def request_context(self):
        return self._request_context


def _client_params(*, elicitation: bool):
    capability = (
        mtypes.ElicitationCapability(form=mtypes.FormElicitationCapability())
        if elicitation
        else None
    )
    return mtypes.InitializeRequestParams(
        protocolVersion="2025-06-18",
        capabilities=mtypes.ClientCapabilities(elicitation=capability),
        clientInfo=mtypes.Implementation(name="pytest-client", version="0"),
    )


def test_client_supports_elicitation_only_when_declared():
    assert _client_supports_elicitation(_FakeSession(client_params=_client_params(elicitation=True)))
    assert not _client_supports_elicitation(_FakeSession(client_params=_client_params(elicitation=False)))
    assert not _client_supports_elicitation(_FakeSession(client_params=None))


def test_request_hitl_approval_accept_true_returns_true():
    session = _FakeSession(
        client_params=_client_params(elicitation=True),
        result=mtypes.ElicitResult(action="accept", content={"approve": True, "reason": "ok"}),
    )
    app = _FakeApp(SimpleNamespace(session=session, request_id="req-1"))
    ctx = GateContext(tool_name="exec_command", arguments={"cmd": "whoami"})

    approved = asyncio.run(_request_hitl_approval(app, ctx))

    assert approved is True
    assert session.calls
    call = session.calls[0]
    assert "exec_command" in call["message"]
    assert call["related_request_id"] == "req-1"


def test_request_hitl_approval_decline_returns_false():
    session = _FakeSession(
        client_params=_client_params(elicitation=True),
        result=mtypes.ElicitResult(action="decline"),
    )
    app = _FakeApp(SimpleNamespace(session=session, request_id="req-1"))

    approved = asyncio.run(_request_hitl_approval(app, GateContext(tool_name="exec_command")))

    assert approved is False


def test_request_hitl_approval_without_capability_returns_none():
    session = _FakeSession(
        client_params=_client_params(elicitation=False),
        result=mtypes.ElicitResult(action="accept", content={"approve": True}),
    )
    app = _FakeApp(SimpleNamespace(session=session, request_id="req-1"))

    approved = asyncio.run(_request_hitl_approval(app, GateContext(tool_name="exec_command")))

    assert approved is None
    assert session.calls == []


class _RequireApprovalPipeline:
    def __init__(self):
        self.resumed = []

    async def run(self, ctx, executor):
        del executor
        return PipelineResult(
            ctx=ctx,
            allowed=False,
            tool_result=None,
            final_decision=Decision.REQUIRE_APPROVAL,
            final_reason="gate2_plan: approval required",
        )

    async def run_after_approval(self, ctx, executor):
        self.resumed.append(ctx)
        result = await executor(ctx)
        return PipelineResult(
            ctx=ctx,
            allowed=True,
            tool_result=result,
            final_decision=Decision.ALLOW,
            final_reason="hitl_approved",
        )


class _FakeRouter:
    def __init__(self):
        self.downstream_calls = []

    def list_tools(self):
        return [
            {
                "name": "exec_command",
                "description": "dangerous",
                "inputSchema": {"type": "object", "properties": {}},
            }
        ]

    async def call_tool(self, ctx):
        self.downstream_calls.append(ctx)
        return "executed"


def test_upstream_calls_downstream_after_elicitation_approval(monkeypatch):
    async def approve(app, ctx):
        del app, ctx
        return True

    monkeypatch.setattr(upstream, "_request_hitl_approval", approve)
    router = _FakeRouter()
    pipeline = _RequireApprovalPipeline()
    app = _build_app(pipeline, router)
    handler = app.request_handlers[mtypes.CallToolRequest]
    req = mtypes.CallToolRequest(
        params=mtypes.CallToolRequestParams(name="exec_command", arguments={"cmd": "whoami"})
    )

    result = asyncio.run(handler(req))

    assert len(router.downstream_calls) == 1
    assert len(pipeline.resumed) == 1
    assert result.root.content[0].text == "executed"


def test_upstream_does_not_call_downstream_after_elicitation_reject(monkeypatch):
    async def reject(app, ctx):
        del app, ctx
        return False

    monkeypatch.setattr(upstream, "_request_hitl_approval", reject)
    router = _FakeRouter()
    app = _build_app(_RequireApprovalPipeline(), router)
    handler = app.request_handlers[mtypes.CallToolRequest]
    req = mtypes.CallToolRequest(
        params=mtypes.CallToolRequestParams(name="exec_command", arguments={"cmd": "whoami"})
    )

    result = asyncio.run(handler(req))

    assert router.downstream_calls == []
    assert "HITL 审批已拒绝" in result.root.content[0].text
