"""集成测试用的最小 MCP stdio server fixture。

提供一个 `echo` 工具：将 arguments 原样回传为文本。仅供 test_proxy_smoke 使用。
被 DownstreamRouter 当作真实下游 MCP server 启动（python -m ...）。
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import mcp.types as mtypes
from mcp.server import Server
from mcp.server.stdio import stdio_server


def _build_app() -> Server:
    app: Server = Server("echo-fixture")

    @app.list_tools()
    async def _list_tools() -> list[mtypes.Tool]:
        return [
            mtypes.Tool(
                name="echo",
                description="echo back arguments as text",
                inputSchema={
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "additionalProperties": True,
                },
            ),
            mtypes.Tool(
                name="exec_command",
                description="pretend to run a shell command (fixture only)",
                inputSchema={
                    "type": "object",
                    "properties": {"cmd": {"type": "string"}},
                    "additionalProperties": True,
                },
            ),
        ]

    @app.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any]) -> list[mtypes.TextContent]:
        payload = json.dumps({"tool": name, "args": arguments}, ensure_ascii=False)
        return [mtypes.TextContent(type="text", text=f"echo:{payload}")]

    return app


async def _main() -> None:
    app = _build_app()
    async with stdio_server() as (r, w):
        await app.run(r, w, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(_main())
