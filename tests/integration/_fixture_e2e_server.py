"""E2E harness 用的下游 MCP stdio server fixture。

比 _fixture_echo_server 多一个 grant_permission 工具，用于触发 Gate2
REQUIRE_APPROVAL（红工具，同步阻塞 HITL）。所有工具都把入参原样回显为
JSON 文本，便于上游断言"下游确实被调用且拿到了正确参数"。

被 DownstreamRouter 当作真实下游 MCP server 启动（python <thisfile>）。
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import mcp.types as mtypes
from mcp.server import Server
from mcp.server.stdio import stdio_server


def _build_app() -> Server:
    app: Server = Server("e2e-fixture")

    @app.list_tools()
    async def _list_tools() -> list[mtypes.Tool]:
        obj = {"type": "object", "properties": {}, "additionalProperties": True}
        return [
            mtypes.Tool(name="echo", description="echo back arguments as text", inputSchema=obj),
            mtypes.Tool(name="exec_command", description="pretend to run a shell command", inputSchema=obj),
            mtypes.Tool(name="grant_permission", description="grant a permission (red / HITL)", inputSchema=obj),
        ]

    @app.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any]) -> list[mtypes.TextContent]:
        payload = json.dumps({"tool": name, "args": arguments}, ensure_ascii=False)
        return [mtypes.TextContent(type="text", text=f"e2e:{payload}")]

    return app


async def _main() -> None:
    app = _build_app()
    async with stdio_server() as (r, w):
        await app.run(r, w, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(_main())
