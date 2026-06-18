"""上游 MCP Server：面向 LLM 客户端（Trae / Cursor / ...）。

实现：mcp>=1.27 server API（Server + stdio_server）。
- @app.list_tools()：聚合 downstream_router 已缓存的工具元数据。
- @app.call_tool()：构造 GateContext，跑 pipeline.run，命中拦截则返回 TextContent 错误，
  放行则把下游 CallToolResult.content 透传出去。

elicitation 最小接入：当客户端声明 elicitation 能力且 pipeline 返回 REQUIRE_APPROVAL，
  server 通过 elicitation/create 请求 approve/reject；approve 后才调用下游 executor。
Streamable HTTP：使用 mcp.server.streamable_http.StreamableHTTPServerTransport
  接 Starlette/uvicorn，作为容器化部署和生产形态的 HTTP MCP 入口。
"""
from __future__ import annotations

import json
import logging
import os
from hmac import compare_digest
from typing import Any

import mcp.types as mtypes
from pydantic import BaseModel, Field
from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

from xa_guard.aibom.gateway import AdmissionResult, admit_install_request
from xa_guard.approval import issue_approval
from xa_guard.pipeline import Pipeline
from xa_guard.proxy.downstream import DownstreamRouter
from xa_guard.proxy.pending import PendingApprovalStore, arguments_are_redacted, redact_arguments
from xa_guard.types import Decision, GateContext, GateResult, InputSource

log = logging.getLogger("xa_guard.proxy.upstream")

_PENDING_LIST_TOOL = "xa_guard_list_pending_approvals"
_PENDING_APPROVE_TOOL = "xa_guard_approve_pending"
_AIBOM_INSTALL_TOOL = "install_plugin"


def _aibom_install_preflight(
    arguments: dict[str, Any], *, offline_store: Any = None
) -> GateResult:
    """Turn an install intent into a pipeline-native, auditable admission result."""
    admission: AdmissionResult = admit_install_request(arguments, offline_store=offline_store)
    remote_not_mirrored = _bom_risk_count(admission.bom, "artifact_remote_fetch_required") > 0
    decision = Decision(admission.decision)
    risks = [admission.reason]
    if remote_not_mirrored:
        # A real execution path must not let a C-grade remote reference reach HITL
        # and then install bytes that were never available to the offline scanner.
        decision = Decision.DENY
        risks.append("remote artifact is absent from the offline AIBOM cache")

    component_hashes = (
        admission.bom.get("metadata", {}).get("component", {}).get("hashes", [])
    )
    component_sha256 = str(component_hashes[0].get("content", "")) if component_hashes else ""
    return GateResult(
        gate_name="aibom_gateway",
        decision=decision,
        risks=risks,
        rule_hits=["AIBOM-GATEWAY"],
        metadata={
            "grade": admission.grade,
            "component": admission.component,
            "component_sha256": component_sha256,
            "schema_valid": admission.schema_valid,
            "vulnerabilities": admission.vulnerabilities,
            "max_vuln_severity": admission.max_vuln_severity,
            "reputation_flags": admission.reputation_flags,
            "remote_not_mirrored": remote_not_mirrored,
        },
    )


def _bom_risk_count(bom: dict[str, Any], risk_name: str) -> int:
    property_name = f"xa_guard:aibom:risk:{risk_name}"
    for prop in bom.get("properties", []):
        if prop.get("name") == property_name:
            try:
                return int(prop.get("value", 0))
            except (TypeError, ValueError):
                return 0
    return 0


class _ApprovalResponse(BaseModel):
    approve: bool = Field(description="是否批准执行该高危工具调用")
    reason: str = Field(default="", description="审批理由，可留空")


class _ApprovalOutcome(BaseModel):
    """HITL 审批结果：是否批准 + 审批人 + 理由。

    approved: True=批准 / False=拒绝 / None=无审批通道（无 request context 或
              客户端不支持 elicitation 或 elicitation 失败）。
    """

    approved: bool | None = None
    approver: str = ""
    reason: str = ""


def _pending_ledger_path(pipeline: Pipeline) -> str:
    env_path = os.getenv("XA_GUARD_PENDING_APPROVAL_STORE")
    if env_path:
        return env_path
    cfg = getattr(pipeline, "cfg", None)
    return str(getattr(cfg, "pending_approvals_path", "") or "")


def _aibom_offline_store() -> Any:
    cache_path = os.getenv("XA_GUARD_AIBOM_OFFLINE_CACHE", "").strip()
    if not cache_path:
        return None
    from xa_guard.aibom.offline_fetch import OfflinePackageStore

    return OfflinePackageStore(cache_path)


def _build_app(pipeline: Pipeline, downstream_router: DownstreamRouter) -> Server:
    app: Server = Server("xa-guard")
    pending = PendingApprovalStore(ledger_path=_pending_ledger_path(pipeline))
    aibom_offline_store = _aibom_offline_store()
    tool_schemas = {
        str(meta.get("name") or ""): dict(meta.get("inputSchema") or {})
        for meta in downstream_router.list_tools()
    }

    @app.list_tools()
    async def _list_tools() -> list[mtypes.Tool]:
        tools: list[mtypes.Tool] = []
        for meta in downstream_router.list_tools():
            tools.append(
                mtypes.Tool(
                    name=meta["name"],
                    description=meta.get("description", ""),
                    inputSchema=meta.get("inputSchema") or {"type": "object", "properties": {}},
                )
            )
        tools.extend(_control_tools())
        return tools

    @app.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any]) -> list[mtypes.TextContent]:
        arguments = arguments or {}

        async def _executor(c: GateContext) -> Any:
            return await downstream_router.call_tool(c)

        if name == _PENDING_LIST_TOOL:
            return _list_pending_approvals(pending, arguments)
        if name == _PENDING_APPROVE_TOOL:
            return await _approve_pending_approval(
                pipeline=pipeline,
                pending=pending,
                arguments=arguments,
                executor=_executor,
            )

        ctx = GateContext(
            tool_name=name,
            arguments=arguments,
            session_history=[],
            input_sources=[InputSource.USER],
        )
        if name == _AIBOM_INSTALL_TOOL:
            ctx.append(
                _aibom_install_preflight(arguments, offline_store=aibom_offline_store)
            )

        result = await pipeline.run(ctx, _executor)

        if result.final_decision == Decision.REQUIRE_APPROVAL:
            outcome = await _request_hitl_approval(
                app,
                ctx,
                input_schema=tool_schemas.get(ctx.tool_name),
            )
            approved = outcome.approved
            if approved is True:
                # 人工已批准：签发可验证审批令牌，挂到 ctx 供 pipeline 验签 + gate6 审计。
                ctx.approval = issue_approval(
                    trace_id=ctx.trace_id,
                    tool_name=ctx.tool_name,
                    arguments=ctx.arguments,
                    approver=outcome.approver or "mcp-elicitation-user",
                    reason=outcome.reason,
                )
                try:
                    resumed = await pipeline.run_after_approval(ctx, _executor)
                    if not resumed.allowed:
                        return [
                            mtypes.TextContent(
                                type="text",
                                text=(
                                    f"⚠ XA-Guard 审批后仍被拦截: {resumed.final_reason}\n"
                                    f"命中规则: {ctx.rule_hits}\n"
                                    f"trace_id={ctx.trace_id}"
                                ),
                            )
                        ]
                    return _to_text_contents(resumed.tool_result)
                except Exception as exc:
                    log.exception("downstream tool failed after HITL approval")
                    return [
                        mtypes.TextContent(
                            type="text",
                            text=f"⚠ XA-Guard 批准后执行失败: {type(exc).__name__}: {exc}",
                        )
                    ]
            if approved is False:
                await pipeline.reject_after_approval(
                    ctx,
                    approver=outcome.approver or "mcp-elicitation-user",
                    reason=outcome.reason,
                )
                return [
                    mtypes.TextContent(
                        type="text",
                        text=(
                            f"⚠ XA-Guard HITL 审批已拒绝: {ctx.tool_name}\n"
                            f"trace_id={ctx.trace_id}"
                        ),
                    )
                ]
            if approved is None:
                item = pending.add(ctx, input_schema=tool_schemas.get(ctx.tool_name))
                return [
                    mtypes.TextContent(
                        type="text",
                        text=(
                            f"⚠ XA-Guard 等待人工审批: {ctx.tool_name}\n"
                            f"trace_id={ctx.trace_id}\n"
                            f"expires_at={item.expires_at.isoformat()}\n"
                            f"调用 {_PENDING_APPROVE_TOOL} 并传入 "
                            '{"trace_id": "...", "approve": true|false, "reason": "..."} '
                            "完成审批。"
                        ),
                    )
                ]

        if not result.allowed:
            text = (
                f"⚠ XA-Guard 已拦截: {result.final_reason}\n"
                f"命中规则: {ctx.rule_hits}\n"
                f"trace_id={ctx.trace_id}"
            )
            return [mtypes.TextContent(type="text", text=text)]

        return _to_text_contents(result.tool_result)

    return app


def _control_tools() -> list[mtypes.Tool]:
    return [
        mtypes.Tool(
            name=_PENDING_LIST_TOOL,
            description="List XA-Guard HITL approvals waiting for manual operator action.",
            inputSchema={
                "type": "object",
                "properties": {"operator_token": {"type": "string"}},
                "additionalProperties": False,
            },
        ),
        mtypes.Tool(
            name=_PENDING_APPROVE_TOOL,
            description="Approve or reject one pending XA-Guard HITL tool call by trace_id.",
            inputSchema={
                "type": "object",
                "properties": {
                    "trace_id": {"type": "string"},
                    "approve": {"type": "boolean"},
                    "approver": {"type": "string"},
                    "reason": {"type": "string"},
                    "operator_token": {"type": "string"},
                },
                "required": ["trace_id", "approve"],
                "additionalProperties": False,
            },
        ),
    ]


def _operator_token_error(arguments: dict[str, Any]) -> mtypes.TextContent | None:
    operator_token = os.getenv("XA_GUARD_APPROVAL_OPERATOR_TOKEN")
    if operator_token and not compare_digest(
        str(arguments.get("operator_token") or ""),
        operator_token,
    ):
        return mtypes.TextContent(
            type="text",
            text="⚠ XA-Guard pending approval operator_token 无效",
        )
    return None


def _list_pending_approvals(
    pending: PendingApprovalStore,
    arguments: dict[str, Any],
) -> list[mtypes.TextContent]:
    token_error = _operator_token_error(arguments)
    if token_error is not None:
        return [token_error]

    items: list[dict[str, Any]] = []
    for item in pending.list():
        ctx = item.ctx
        items.append(
            {
                "trace_id": ctx.trace_id,
                "tool_name": ctx.tool_name,
                "arguments": redact_arguments(ctx.arguments, item.input_schema),
                "created_at": item.created_at.isoformat(),
                "expires_at": item.expires_at.isoformat(),
                "final_reason": ctx.final_reason,
                "risk_level": ctx.risk_level.value if ctx.risk_level else "",
                "rule_hits": list(ctx.rule_hits),
            }
        )
    return [
        mtypes.TextContent(
            type="text",
            text=json.dumps({"pending_approvals": items}, ensure_ascii=False),
        )
    ]


async def _approve_pending_approval(
    *,
    pipeline: Pipeline,
    pending: PendingApprovalStore,
    arguments: dict[str, Any],
    executor: Any,
) -> list[mtypes.TextContent]:
    trace_id = str(arguments.get("trace_id") or "")
    if not trace_id:
        return [mtypes.TextContent(type="text", text="⚠ XA-Guard pending approval 缺少 trace_id")]

    token_error = _operator_token_error(arguments)
    if token_error is not None:
        return [token_error]

    approved = bool(arguments.get("approve"))
    item = pending.pop(trace_id, outcome="approved" if approved else "rejected")
    if item is None:
        return [
            mtypes.TextContent(
                type="text",
                text=f"⚠ XA-Guard pending approval 不存在或已过期: trace_id={trace_id}",
            )
        ]

    ctx = item.ctx
    reason = str(arguments.get("reason") or "")
    approver = str(arguments.get("approver") or "mcp-pending-approval-user")

    if not approved:
        await pipeline.reject_after_approval(ctx, approver=approver, reason=reason)
        return [
            mtypes.TextContent(
                type="text",
                text=(
                    f"⚠ XA-Guard HITL 审批已拒绝: {ctx.tool_name}\n"
                    f"trace_id={ctx.trace_id}"
                ),
            )
        ]

    if arguments_are_redacted(ctx.arguments):
        await pipeline.reject_after_approval(
            ctx,
            approver=approver,
            reason="pending_arguments_redacted_after_restart",
        )
        return [
            mtypes.TextContent(
                type="text",
                text=(
                    "⚠ XA-Guard pending approval 参数已在本地 ledger 中脱敏，"
                    "无法在重启恢复后安全执行；请重新发起该工具调用并重新审批。"
                ),
            )
        ]

    ctx.approval = issue_approval(
        trace_id=ctx.trace_id,
        tool_name=ctx.tool_name,
        arguments=ctx.arguments,
        approver=approver,
        reason=reason,
    )
    try:
        resumed = await pipeline.run_after_approval(ctx, executor)
        if not resumed.allowed:
            return [
                mtypes.TextContent(
                    type="text",
                    text=(
                        f"⚠ XA-Guard 审批后仍被拦截: {resumed.final_reason}\n"
                        f"命中规则: {ctx.rule_hits}\n"
                        f"trace_id={ctx.trace_id}"
                    ),
                )
            ]
        return _to_text_contents(resumed.tool_result)
    except Exception as exc:
        log.exception("downstream tool failed after pending HITL approval")
        return [
            mtypes.TextContent(
                type="text",
                text=f"⚠ XA-Guard 批准后执行失败: {type(exc).__name__}: {exc}",
            )
        ]


def _client_supports_elicitation(session: Any) -> bool:
    client_params = getattr(session, "client_params", None)
    capabilities = getattr(client_params, "capabilities", None)
    elicitation = getattr(capabilities, "elicitation", None)
    return elicitation is not None


def _approver_identity(session: Any) -> str:
    """从客户端 client info 推断审批人身份，缺失时给占位。"""
    client_params = getattr(session, "client_params", None)
    client_info = getattr(client_params, "clientInfo", None)
    name = getattr(client_info, "name", None)
    return str(name) if name else "mcp-elicitation-user"


async def _request_hitl_approval(
    app: Server,
    ctx: GateContext,
    input_schema: dict[str, Any] | None = None,
) -> _ApprovalOutcome:
    """Request approve/reject via MCP elicitation if the current client supports it.

    Returns _ApprovalOutcome:
        approved=True:  client accepted and approved (approver/reason filled).
        approved=False: client declined/cancelled or accepted with approve=False.
        approved=None:  no request context, no elicitation capability, or failed.
    """
    try:
        request_context = app.request_context
    except LookupError:
        return _ApprovalOutcome(approved=None)

    session = request_context.session
    if not _client_supports_elicitation(session):
        return _ApprovalOutcome(approved=None)

    approver = _approver_identity(session)
    message = (
        "XA-Guard 需要人工审批高危工具调用。\n"
        f"tool: {ctx.tool_name}\n"
        f"arguments: {redact_arguments(ctx.arguments, input_schema)}\n"
        f"trace_id: {ctx.trace_id}\n"
        "请选择 approve=true 才会继续执行。"
    )
    try:
        result = await session.elicit_form(
            message=message,
            requestedSchema=_ApprovalResponse.model_json_schema(),
            related_request_id=getattr(request_context, "request_id", None),
        )
    except Exception as exc:
        log.warning("MCP elicitation approval request failed: %s", exc)
        return _ApprovalOutcome(approved=None)

    if result.action != "accept":
        return _ApprovalOutcome(approved=False, approver=approver)
    try:
        response = _ApprovalResponse.model_validate(result.content or {})
    except Exception as exc:
        log.warning("MCP elicitation approval response invalid: %s", exc)
        return _ApprovalOutcome(approved=False, approver=approver)
    return _ApprovalOutcome(approved=response.approve, approver=approver, reason=response.reason)


def _to_text_contents(tool_result: Any) -> list[mtypes.TextContent]:
    """把下游 call_tool 返回的对象规整成 list[TextContent]。

    - mcp.types.CallToolResult: 透传 content（仅取 TextContent；其它类型转字符串）
    - list/tuple: 逐项规整
    - str/其它: 字符串化
    """
    if tool_result is None:
        return [mtypes.TextContent(type="text", text="")]
    if isinstance(tool_result, mtypes.CallToolResult):
        out: list[mtypes.TextContent] = []
        for block in tool_result.content or []:
            if isinstance(block, mtypes.TextContent):
                out.append(block)
            else:
                out.append(mtypes.TextContent(type="text", text=str(block)))
        if not out:
            out.append(mtypes.TextContent(type="text", text=""))
        return out
    if isinstance(tool_result, mtypes.TextContent):
        return [tool_result]
    if isinstance(tool_result, (list, tuple)):
        result: list[mtypes.TextContent] = []
        for item in tool_result:
            result.extend(_to_text_contents(item))
        return result or [mtypes.TextContent(type="text", text="")]
    return [mtypes.TextContent(type="text", text=str(tool_result))]


async def run_stdio(pipeline: Pipeline, downstream_router: DownstreamRouter) -> None:
    """启动 stdio MCP server，阻塞直到客户端断开。"""
    app = _build_app(pipeline, downstream_router)
    init_opts: InitializationOptions = app.create_initialization_options()
    async with stdio_server() as (read_stream, write_stream):
        log.info("xa-guard stdio server started")
        await app.run(read_stream, write_stream, init_opts)


async def run_streamable_http(
    pipeline: Pipeline,
    downstream_router: DownstreamRouter,
    host: str = "127.0.0.1",
    port: int = 3000,
) -> None:
    """启动 Streamable HTTP MCP server，阻塞直到 uvicorn 退出。"""
    try:
        import anyio
        import uvicorn
        from mcp.server.streamable_http import (
            StreamableHTTPServerTransport,
            TransportSecuritySettings,
        )
        from starlette.applications import Starlette
        from starlette.responses import JSONResponse
        from starlette.routing import Mount, Route
    except Exception as exc:  # pragma: no cover - exercised only when optional deps are absent
        raise RuntimeError(
            "Streamable HTTP upstream requires xa-guard[http] "
            "(starlette + uvicorn + mcp streamable_http transport)"
        ) from exc

    mcp_app = _build_app(pipeline, downstream_router)
    init_opts: InitializationOptions = mcp_app.create_initialization_options()

    allowed_hosts = [
        host,
        f"{host}:{port}",
        "127.0.0.1",
        f"127.0.0.1:{port}",
        "localhost",
        f"localhost:{port}",
    ]
    if host in {"0.0.0.0", "::"}:
        allowed_hosts.extend(
            [
                "0.0.0.0",
                f"0.0.0.0:{port}",
                "localhost",
                f"localhost:{port}",
                "127.0.0.1",
                f"127.0.0.1:{port}",
            ]
        )
    transport = StreamableHTTPServerTransport(
        mcp_session_id=None,
        is_json_response_enabled=False,
        security_settings=TransportSecuritySettings(allowed_hosts=sorted(set(allowed_hosts))),
    )

    async def _healthz(_request):
        return JSONResponse({"status": "ok", "transport": "streamable-http"})

    asgi_app = Starlette(
        routes=[
            Route("/healthz", endpoint=_healthz, methods=["GET"]),
            Mount("/mcp", app=transport.handle_request),
            Mount("/", app=transport.handle_request),
        ]
    )
    config = uvicorn.Config(asgi_app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)

    log.info("xa-guard Streamable HTTP server starting on http://%s:%s/mcp", host, port)
    async with transport.connect() as (read_stream, write_stream):
        async with anyio.create_task_group() as tg:
            tg.start_soon(mcp_app.run, read_stream, write_stream, init_opts)
            tg.start_soon(server.serve)
