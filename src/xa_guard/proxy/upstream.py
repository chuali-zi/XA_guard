"""上游 MCP Server：面向 LLM 客户端（Trae / Cursor / ...）。

实现：mcp>=1.27 server API（Server + stdio_server）。
- @app.list_tools()：聚合 downstream_router 已缓存的工具元数据。
- @app.call_tool()：构造 GateContext，跑 pipeline.run，命中拦截则返回 TextContent 错误，
  放行则把下游 CallToolResult.content 透传出去。

elicitation 最小接入：当客户端声明 elicitation 能力且 pipeline 返回 REQUIRE_APPROVAL，
  server 通过 elicitation/create 请求 approve/reject；approve 后才调用下游 executor。
Streamable HTTP 占位：当前 mcp 1.27 暴露的是 StreamableHTTPServerTransport 低层，
  需结合 ASGI 框架（Starlette/uvicorn），demo 阶段先 NotImplementedError。
"""
from __future__ import annotations

import logging
from typing import Any

import mcp.types as mtypes
from pydantic import BaseModel, Field
from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

from xa_guard.pipeline import Pipeline
from xa_guard.proxy.downstream import DownstreamRouter
from xa_guard.types import Decision, GateContext, InputSource

log = logging.getLogger("xa_guard.proxy.upstream")


class _ApprovalResponse(BaseModel):
    approve: bool = Field(description="是否批准执行该高危工具调用")
    reason: str = Field(default="", description="审批理由，可留空")


def _build_app(pipeline: Pipeline, downstream_router: DownstreamRouter) -> Server:
    app: Server = Server("xa-guard")

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
        return tools

    @app.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any]) -> list[mtypes.TextContent]:
        ctx = GateContext(
            tool_name=name,
            arguments=arguments or {},
            session_history=[],
            input_sources=[InputSource.USER],
        )

        async def _executor(c: GateContext) -> Any:
            return await downstream_router.call_tool(c)

        result = await pipeline.run(ctx, _executor)

        if result.final_decision == Decision.REQUIRE_APPROVAL:
            approved = await _request_hitl_approval(app, ctx)
            if approved is True:
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
                return [
                    mtypes.TextContent(
                        type="text",
                        text=(
                            f"⚠ XA-Guard HITL 审批已拒绝: {ctx.tool_name}\n"
                            f"trace_id={ctx.trace_id}"
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


def _client_supports_elicitation(session: Any) -> bool:
    client_params = getattr(session, "client_params", None)
    capabilities = getattr(client_params, "capabilities", None)
    elicitation = getattr(capabilities, "elicitation", None)
    return elicitation is not None


async def _request_hitl_approval(app: Server, ctx: GateContext) -> bool | None:
    """Request approve/reject via MCP elicitation if the current client supports it.

    Returns:
        True: client accepted and approved.
        False: client declined/cancelled or accepted with approve=False.
        None: no request context, no elicitation capability, or elicitation failed.
    """
    try:
        request_context = app.request_context
    except LookupError:
        return None

    session = request_context.session
    if not _client_supports_elicitation(session):
        return None

    message = (
        "XA-Guard 需要人工审批高危工具调用。\n"
        f"tool: {ctx.tool_name}\n"
        f"arguments: {ctx.arguments}\n"
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
        return None

    if result.action != "accept":
        return False
    try:
        response = _ApprovalResponse.model_validate(result.content or {})
    except Exception as exc:
        log.warning("MCP elicitation approval response invalid: %s", exc)
        return False
    return response.approve


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
    """Streamable HTTP MCP server 占位。

    mcp 1.27 暴露的是 StreamableHTTPServerTransport 低层，需结合 ASGI 框架接入。
    demo 阶段优先 stdio，HTTP 接入留至后续迭代。
    """
    # TODO(agent-P): 用 mcp.server.streamable_http.StreamableHTTPServerTransport
    # + Starlette/uvicorn 实现 HTTP 接入。
    raise NotImplementedError(
        "run_streamable_http 暂未实现，请使用 run_stdio（mcp>=1.27 stdio 已稳定）"
    )
