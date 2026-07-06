"""Minimal downstream MCP server for XA-Guard live SUT checks.

The server exposes the current ToolSurface schemas and echoes tool calls. The
range runner keeps authoritative world mutation in-process after XA-Guard allows
the call; this downstream exists so the real XA-Guard MCP pipeline can inspect
and audit every tool attempt.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any


def load_tools(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("tool schema file must contain a list")
    return [tool for tool in data if isinstance(tool, dict) and tool.get("name")]


def build_app(tools: list[dict[str, Any]]):
    try:
        import mcp.types as mtypes
        from mcp.server import Server
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("open-agent-range live XA-Guard echo server requires mcp") from exc

    app = Server("open-agent-range-echo", version="0.1.0")
    by_name = {str(tool["name"]): tool for tool in tools}

    @app.list_tools()
    async def _list_tools() -> list[mtypes.Tool]:
        return [
            mtypes.Tool(
                name=str(tool["name"]),
                description=str(tool.get("description") or ""),
                inputSchema=tool.get("inputSchema") or {"type": "object", "properties": {}},
            )
            for tool in tools
        ]

    @app.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any]) -> list[mtypes.TextContent]:
        if name not in by_name:
            payload = {"error": f"unknown tool: {name}", "tool": name}
        else:
            payload = {"ok": True, "tool": name, "arguments": dict(arguments or {})}
        return [mtypes.TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, sort_keys=True))]

    return app


async def serve_stdio(*, tools_path: Path) -> None:
    try:
        from mcp.server.stdio import stdio_server
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("open-agent-range live XA-Guard echo server requires mcp") from exc

    app = build_app(load_tools(tools_path))
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="open-agent-range MCP echo server")
    parser.add_argument("--tools", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    asyncio.run(serve_stdio(tools_path=args.tools))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
