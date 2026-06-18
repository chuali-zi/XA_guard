"""Unit tests for upstream HITL elicitation helpers."""
from __future__ import annotations

import asyncio
import json
import re
from types import SimpleNamespace

from mcp import types as mtypes

from xa_guard.proxy import upstream
from xa_guard.proxy.upstream import (
    _aibom_install_preflight,
    _build_app,
    _client_supports_elicitation,
    _request_hitl_approval,
)
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


def test_aibom_remote_install_without_offline_mirror_fails_closed():
    result = _aibom_install_preflight({"url": "https://example.invalid/plugin.zip"})

    assert result.decision == Decision.DENY
    assert result.gate_name == "aibom_gateway"
    assert result.rule_hits == ["AIBOM-GATEWAY"]
    assert result.metadata["grade"] == "C"
    assert result.metadata["remote_not_mirrored"] is True


def test_request_hitl_approval_accept_true_returns_true():
    session = _FakeSession(
        client_params=_client_params(elicitation=True),
        result=mtypes.ElicitResult(action="accept", content={"approve": True, "reason": "ok"}),
    )
    app = _FakeApp(SimpleNamespace(session=session, request_id="req-1"))
    ctx = GateContext(tool_name="exec_command", arguments={"cmd": "whoami"})

    outcome = asyncio.run(_request_hitl_approval(app, ctx))

    assert outcome.approved is True
    assert outcome.approver == "pytest-client"
    assert outcome.reason == "ok"
    assert session.calls
    call = session.calls[0]
    assert "exec_command" in call["message"]
    assert call["related_request_id"] == "req-1"


def test_request_hitl_approval_redacts_schema_marked_arguments_in_message():
    session = _FakeSession(
        client_params=_client_params(elicitation=True),
        result=mtypes.ElicitResult(action="accept", content={"approve": True, "reason": "ok"}),
    )
    app = _FakeApp(SimpleNamespace(session=session, request_id="req-1"))
    ctx = GateContext(
        tool_name="exec_command",
        arguments={"cmd": "whoami", "tenant": "finance-bureau"},
    )
    schema = {
        "type": "object",
        "properties": {
            "cmd": {"type": "string"},
            "tenant": {"type": "string", "x-xa-guard-sensitive": True},
        },
    }

    asyncio.run(_request_hitl_approval(app, ctx, input_schema=schema))

    message = session.calls[0]["message"]
    assert "finance-bureau" not in message
    assert "[REDACTED]:sha256:" in message
    assert "whoami" in message


def test_request_hitl_approval_decline_returns_false():
    session = _FakeSession(
        client_params=_client_params(elicitation=True),
        result=mtypes.ElicitResult(action="decline"),
    )
    app = _FakeApp(SimpleNamespace(session=session, request_id="req-1"))

    outcome = asyncio.run(_request_hitl_approval(app, GateContext(tool_name="exec_command")))

    assert outcome.approved is False


def test_request_hitl_approval_without_capability_returns_none():
    session = _FakeSession(
        client_params=_client_params(elicitation=False),
        result=mtypes.ElicitResult(action="accept", content={"approve": True}),
    )
    app = _FakeApp(SimpleNamespace(session=session, request_id="req-1"))

    outcome = asyncio.run(_request_hitl_approval(app, GateContext(tool_name="exec_command")))

    assert outcome.approved is None
    assert session.calls == []


class _RequireApprovalPipeline:
    def __init__(self):
        self.resumed = []
        self.rejected = []

    async def run(self, ctx, executor):
        del executor
        ctx.final_decision = Decision.REQUIRE_APPROVAL
        ctx.final_reason = "gate2_plan: approval required"
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

    async def reject_after_approval(self, ctx, *, approver="", reason=""):
        ctx.final_decision = Decision.DENY
        ctx.final_reason = "hitl_rejected" if not reason else f"hitl_rejected: {reason}"
        self.rejected.append((ctx, approver, reason))
        return PipelineResult(
            ctx=ctx,
            allowed=False,
            tool_result=None,
            final_decision=Decision.DENY,
            final_reason=ctx.final_reason,
        )


class _FakeRouter:
    def __init__(self, input_schema=None):
        self.downstream_calls = []
        self.input_schema = input_schema or {"type": "object", "properties": {}}

    def list_tools(self):
        return [
            {
                "name": "exec_command",
                "description": "dangerous",
                "inputSchema": self.input_schema,
            }
        ]

    async def call_tool(self, ctx):
        self.downstream_calls.append(ctx)
        return "executed"


def test_upstream_calls_downstream_after_elicitation_approval(monkeypatch):
    async def approve(app, ctx, **_kwargs):
        del app, ctx
        return upstream._ApprovalOutcome(approved=True, approver="pytest-client", reason="ok")

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
    async def reject(app, ctx, **_kwargs):
        del app, ctx
        return upstream._ApprovalOutcome(approved=False, approver="pytest-client")

    monkeypatch.setattr(upstream, "_request_hitl_approval", reject)
    router = _FakeRouter()
    pipeline = _RequireApprovalPipeline()
    app = _build_app(pipeline, router)
    handler = app.request_handlers[mtypes.CallToolRequest]
    req = mtypes.CallToolRequest(
        params=mtypes.CallToolRequestParams(name="exec_command", arguments={"cmd": "whoami"})
    )

    result = asyncio.run(handler(req))

    assert router.downstream_calls == []
    assert len(pipeline.rejected) == 1
    assert pipeline.rejected[0][1] == "pytest-client"
    assert "HITL 审批已拒绝" in result.root.content[0].text


def _call_tool(handler, name: str, arguments: dict | None = None):
    req = mtypes.CallToolRequest(
        params=mtypes.CallToolRequestParams(name=name, arguments=arguments or {})
    )
    return asyncio.run(handler(req))


def _trace_id(text: str) -> str:
    match = re.search(r"trace_id=([0-9a-f-]+)", text)
    assert match, text
    return match.group(1)


def test_upstream_stores_pending_when_no_elicitation_channel(monkeypatch):
    async def unavailable(app, ctx, **_kwargs):
        del app, ctx
        return upstream._ApprovalOutcome(approved=None)

    monkeypatch.setattr(upstream, "_request_hitl_approval", unavailable)
    router = _FakeRouter()
    app = _build_app(_RequireApprovalPipeline(), router)
    handler = app.request_handlers[mtypes.CallToolRequest]

    result = _call_tool(handler, "exec_command", {"cmd": "whoami"})
    text = result.root.content[0].text
    trace_id = _trace_id(text)

    assert router.downstream_calls == []
    assert "等待人工审批" in text
    listed = _call_tool(handler, "xa_guard_list_pending_approvals")
    payload = json.loads(listed.root.content[0].text)
    assert [item["trace_id"] for item in payload["pending_approvals"]] == [trace_id]
    assert payload["pending_approvals"][0]["tool_name"] == "exec_command"
    assert payload["pending_approvals"][0]["arguments"] == {"cmd": "whoami"}


def test_upstream_approves_pending_once_when_no_elicitation_channel(monkeypatch):
    async def unavailable(app, ctx, **_kwargs):
        del app, ctx
        return upstream._ApprovalOutcome(approved=None)

    monkeypatch.setattr(upstream, "_request_hitl_approval", unavailable)
    router = _FakeRouter()
    pipeline = _RequireApprovalPipeline()
    app = _build_app(pipeline, router)
    handler = app.request_handlers[mtypes.CallToolRequest]

    pending = _call_tool(handler, "exec_command", {"cmd": "whoami"})
    trace_id = _trace_id(pending.root.content[0].text)

    approved = _call_tool(
        handler,
        "xa_guard_approve_pending",
        {
            "trace_id": trace_id,
            "approve": True,
            "approver": "pytest-operator",
            "reason": "ok",
        },
    )
    replay = _call_tool(
        handler,
        "xa_guard_approve_pending",
        {"trace_id": trace_id, "approve": True, "reason": "again"},
    )

    assert approved.root.content[0].text == "executed"
    assert len(router.downstream_calls) == 1
    assert len(pipeline.resumed) == 1
    assert pipeline.resumed[0].tool_name == "exec_command"
    assert pipeline.resumed[0].approval is not None
    assert pipeline.resumed[0].approval.token
    assert pipeline.resumed[0].approval.approver == "pytest-operator"
    assert pipeline.resumed[0].approval.reason == "ok"
    assert "不存在或已过期" in replay.root.content[0].text


def test_upstream_pending_operator_token_is_enforced_when_configured(monkeypatch):
    async def unavailable(app, ctx, **_kwargs):
        del app, ctx
        return upstream._ApprovalOutcome(approved=None)

    monkeypatch.setenv("XA_GUARD_APPROVAL_OPERATOR_TOKEN", "secret-token")
    monkeypatch.setattr(upstream, "_request_hitl_approval", unavailable)
    router = _FakeRouter()
    app = _build_app(_RequireApprovalPipeline(), router)
    handler = app.request_handlers[mtypes.CallToolRequest]

    pending = _call_tool(handler, "exec_command", {"cmd": "whoami"})
    trace_id = _trace_id(pending.root.content[0].text)

    denied = _call_tool(
        handler,
        "xa_guard_approve_pending",
        {"trace_id": trace_id, "approve": True, "operator_token": "wrong"},
    )
    list_denied = _call_tool(handler, "xa_guard_list_pending_approvals")
    listed = _call_tool(
        handler,
        "xa_guard_list_pending_approvals",
        {"operator_token": "secret-token"},
    )
    approved = _call_tool(
        handler,
        "xa_guard_approve_pending",
        {"trace_id": trace_id, "approve": True, "operator_token": "secret-token"},
    )

    assert "operator_token 无效" in denied.root.content[0].text
    assert "operator_token 无效" in list_denied.root.content[0].text
    assert json.loads(listed.root.content[0].text)["pending_approvals"][0]["trace_id"] == trace_id
    assert approved.root.content[0].text == "executed"
    assert len(router.downstream_calls) == 1


def test_upstream_rejects_pending_without_downstream_call(monkeypatch):
    async def unavailable(app, ctx, **_kwargs):
        del app, ctx
        return upstream._ApprovalOutcome(approved=None)

    monkeypatch.setattr(upstream, "_request_hitl_approval", unavailable)
    router = _FakeRouter()
    pipeline = _RequireApprovalPipeline()
    app = _build_app(pipeline, router)
    handler = app.request_handlers[mtypes.CallToolRequest]

    pending = _call_tool(handler, "exec_command", {"cmd": "whoami"})
    trace_id = _trace_id(pending.root.content[0].text)
    rejected = _call_tool(
        handler,
        "xa_guard_approve_pending",
        {"trace_id": trace_id, "approve": False, "reason": "no"},
    )

    assert "HITL 审批已拒绝" in rejected.root.content[0].text
    assert router.downstream_calls == []
    assert pipeline.resumed == []
    assert len(pipeline.rejected) == 1
    assert pipeline.rejected[0][2] == "no"
    listed = _call_tool(handler, "xa_guard_list_pending_approvals")
    assert json.loads(listed.root.content[0].text)["pending_approvals"] == []


def test_upstream_pending_ledger_survives_app_restart(monkeypatch, tmp_path):
    async def unavailable(app, ctx, **_kwargs):
        del app, ctx
        return upstream._ApprovalOutcome(approved=None)

    ledger = tmp_path / "pending.jsonl"
    monkeypatch.setenv("XA_GUARD_PENDING_APPROVAL_STORE", str(ledger))
    monkeypatch.setattr(upstream, "_request_hitl_approval", unavailable)

    first_router = _FakeRouter()
    first_app = _build_app(_RequireApprovalPipeline(), first_router)
    first_handler = first_app.request_handlers[mtypes.CallToolRequest]
    pending = _call_tool(first_handler, "exec_command", {"cmd": "whoami"})
    trace_id = _trace_id(pending.root.content[0].text)

    second_router = _FakeRouter()
    second_pipeline = _RequireApprovalPipeline()
    second_app = _build_app(second_pipeline, second_router)
    second_handler = second_app.request_handlers[mtypes.CallToolRequest]

    listed = _call_tool(second_handler, "xa_guard_list_pending_approvals")
    approved = _call_tool(
        second_handler,
        "xa_guard_approve_pending",
        {
            "trace_id": trace_id,
            "approve": True,
            "approver": "pytest-operator",
            "reason": "after-restart",
        },
    )
    replay = _call_tool(
        second_handler,
        "xa_guard_approve_pending",
        {"trace_id": trace_id, "approve": True},
    )

    payload = json.loads(listed.root.content[0].text)
    assert [item["trace_id"] for item in payload["pending_approvals"]] == [trace_id]
    assert payload["pending_approvals"][0]["final_reason"] == "gate2_plan: approval required"
    assert approved.root.content[0].text == "executed"
    assert second_router.downstream_calls[0].trace_id == trace_id
    assert second_pipeline.resumed[0].approval is not None
    assert second_pipeline.resumed[0].approval.approver == "pytest-operator"
    assert second_pipeline.resumed[0].approval.reason == "after-restart"
    assert "不存在或已过期" in replay.root.content[0].text
    text = ledger.read_text(encoding="utf-8")
    assert "approval_token" not in text
    assert second_pipeline.resumed[0].approval.token not in text


def test_upstream_pending_ledger_redacts_list_and_file_but_current_process_can_approve(monkeypatch, tmp_path):
    async def unavailable(app, ctx, **_kwargs):
        del app, ctx
        return upstream._ApprovalOutcome(approved=None)

    ledger = tmp_path / "pending.jsonl"
    monkeypatch.setenv("XA_GUARD_PENDING_APPROVAL_STORE", str(ledger))
    monkeypatch.setattr(upstream, "_request_hitl_approval", unavailable)
    router = _FakeRouter()
    pipeline = _RequireApprovalPipeline()
    app = _build_app(pipeline, router)
    handler = app.request_handlers[mtypes.CallToolRequest]

    pending = _call_tool(
        handler,
        "exec_command",
        {"cmd": "whoami", "password": "p@ssw0rd", "headers": {"Authorization": "Bearer secret"}},
    )
    trace_id = _trace_id(pending.root.content[0].text)
    listed = _call_tool(handler, "xa_guard_list_pending_approvals")
    approved = _call_tool(
        handler,
        "xa_guard_approve_pending",
        {"trace_id": trace_id, "approve": True},
    )

    listed_args = json.loads(listed.root.content[0].text)["pending_approvals"][0]["arguments"]
    ledger_text = ledger.read_text(encoding="utf-8")
    assert listed_args["password"].startswith("[REDACTED]:sha256:")
    assert listed_args["headers"]["Authorization"].startswith("[REDACTED]:sha256:")
    assert "p@ssw0rd" not in ledger_text
    assert "Bearer secret" not in ledger_text
    assert approved.root.content[0].text == "executed"
    assert router.downstream_calls[0].arguments["password"] == "p@ssw0rd"
    assert pipeline.resumed[0].approval is not None
    assert pipeline.resumed[0].approval.token not in ledger_text


def test_upstream_pending_ledger_uses_tool_schema_for_list_and_file(monkeypatch, tmp_path):
    async def unavailable(app, ctx, **_kwargs):
        del app, ctx
        return upstream._ApprovalOutcome(approved=None)

    schema = {
        "type": "object",
        "properties": {
            "cmd": {"type": "string"},
            "tenant": {"type": "string", "x-xa-guard-sensitive": True},
            "rows": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "internal_code": {"type": "string", "writeOnly": True},
                    },
                },
            },
        },
    }
    ledger = tmp_path / "pending.jsonl"
    monkeypatch.setenv("XA_GUARD_PENDING_APPROVAL_STORE", str(ledger))
    monkeypatch.setattr(upstream, "_request_hitl_approval", unavailable)
    router = _FakeRouter(input_schema=schema)
    pipeline = _RequireApprovalPipeline()
    app = _build_app(pipeline, router)
    handler = app.request_handlers[mtypes.CallToolRequest]

    pending = _call_tool(
        handler,
        "exec_command",
        {
            "cmd": "whoami",
            "tenant": "finance-bureau",
            "rows": [{"label": "first", "internal_code": "C-001"}],
        },
    )
    trace_id = _trace_id(pending.root.content[0].text)
    listed = _call_tool(handler, "xa_guard_list_pending_approvals")
    approved = _call_tool(handler, "xa_guard_approve_pending", {"trace_id": trace_id, "approve": True})

    listed_args = json.loads(listed.root.content[0].text)["pending_approvals"][0]["arguments"]
    ledger_text = ledger.read_text(encoding="utf-8")
    assert listed_args["tenant"].startswith("[REDACTED]:sha256:")
    assert listed_args["rows"][0]["internal_code"].startswith("[REDACTED]:sha256:")
    assert listed_args["cmd"] == "whoami"
    assert "finance-bureau" not in ledger_text
    assert "C-001" not in ledger_text
    assert approved.root.content[0].text == "executed"
    assert router.downstream_calls[0].arguments["tenant"] == "finance-bureau"
    assert router.downstream_calls[0].arguments["rows"][0]["internal_code"] == "C-001"


def test_upstream_pending_ledger_redacted_restart_approve_fails_closed(monkeypatch, tmp_path):
    async def unavailable(app, ctx, **_kwargs):
        del app, ctx
        return upstream._ApprovalOutcome(approved=None)

    ledger = tmp_path / "pending.jsonl"
    monkeypatch.setenv("XA_GUARD_PENDING_APPROVAL_STORE", str(ledger))
    monkeypatch.setattr(upstream, "_request_hitl_approval", unavailable)

    first_app = _build_app(_RequireApprovalPipeline(), _FakeRouter())
    first_handler = first_app.request_handlers[mtypes.CallToolRequest]
    pending = _call_tool(
        first_handler,
        "exec_command",
        {"cmd": "whoami", "password": "p@ssw0rd"},
    )
    trace_id = _trace_id(pending.root.content[0].text)

    second_router = _FakeRouter()
    second_pipeline = _RequireApprovalPipeline()
    second_app = _build_app(second_pipeline, second_router)
    second_handler = second_app.request_handlers[mtypes.CallToolRequest]
    approved = _call_tool(
        second_handler,
        "xa_guard_approve_pending",
        {"trace_id": trace_id, "approve": True},
    )

    assert "参数已在本地 ledger 中脱敏" in approved.root.content[0].text
    assert second_router.downstream_calls == []
    assert second_pipeline.resumed == []
    assert len(second_pipeline.rejected) == 1
    assert second_pipeline.rejected[0][2] == "pending_arguments_redacted_after_restart"
    assert "p@ssw0rd" not in ledger.read_text(encoding="utf-8")


def test_upstream_pending_ledger_reject_after_restart(monkeypatch, tmp_path):
    async def unavailable(app, ctx, **_kwargs):
        del app, ctx
        return upstream._ApprovalOutcome(approved=None)

    ledger = tmp_path / "pending.jsonl"
    monkeypatch.setenv("XA_GUARD_PENDING_APPROVAL_STORE", str(ledger))
    monkeypatch.setattr(upstream, "_request_hitl_approval", unavailable)

    first_app = _build_app(_RequireApprovalPipeline(), _FakeRouter())
    first_handler = first_app.request_handlers[mtypes.CallToolRequest]
    pending = _call_tool(first_handler, "exec_command", {"cmd": "whoami"})
    trace_id = _trace_id(pending.root.content[0].text)

    second_router = _FakeRouter()
    second_pipeline = _RequireApprovalPipeline()
    second_app = _build_app(second_pipeline, second_router)
    second_handler = second_app.request_handlers[mtypes.CallToolRequest]
    rejected = _call_tool(
        second_handler,
        "xa_guard_approve_pending",
        {"trace_id": trace_id, "approve": False, "reason": "after-restart-no"},
    )

    assert "HITL 审批已拒绝" in rejected.root.content[0].text
    assert second_router.downstream_calls == []
    assert second_pipeline.resumed == []
    assert len(second_pipeline.rejected) == 1
    assert second_pipeline.rejected[0][0].trace_id == trace_id
    assert second_pipeline.rejected[0][2] == "after-restart-no"
    listed = _call_tool(second_handler, "xa_guard_list_pending_approvals")
    assert json.loads(listed.root.content[0].text)["pending_approvals"] == []
