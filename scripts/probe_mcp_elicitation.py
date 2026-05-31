"""Automated protocol probe for demo.elicitation_probe_server.

This uses mcp.ClientSession with an elicitation_callback, so it validates the
server/client protocol path but does not prove that an IDE rendered a popup.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.session import RequestContext
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp import types as mtypes


ROOT = Path(__file__).resolve().parents[1]


async def _run_probe(approve: bool) -> dict[str, Any]:
    elicitation_events: list[dict[str, Any]] = []

    async def elicitation_callback(
        context: RequestContext[ClientSession, Any],
        params: mtypes.ElicitRequestParams,
    ) -> mtypes.ElicitResult:
        del context
        content = {"approve": approve, "reason": "automated probe"}
        elicitation_events.append(
            {
                "message": getattr(params, "message", ""),
                "requestedSchema": getattr(params, "requestedSchema", {}),
                "content": content,
            }
        )
        return mtypes.ElicitResult(action="accept", content=content)

    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "demo.elicitation_probe_server"],
        cwd=ROOT,
    )
    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(
            read_stream,
            write_stream,
            elicitation_callback=elicitation_callback,
            client_info=mtypes.Implementation(name="xa-guard-toy-probe", version="0.1"),
        ) as session:
            init = await session.initialize()
            tools = await session.list_tools()
            result = await session.call_tool("dangerous_echo", {"payload": "hello"})

    return {
        "mcp_protocol_version": init.protocolVersion,
        "tools": [tool.name for tool in tools.tools],
        "elicitation_events": elicitation_events,
        "tool_text": [block.text for block in result.content if hasattr(block, "text")],
        "is_error": result.isError,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reject", action="store_true", help="return approve=false")
    args = parser.parse_args()
    output = asyncio.run(_run_probe(approve=not args.reject))
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
