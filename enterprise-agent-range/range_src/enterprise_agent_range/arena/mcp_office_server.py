from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from enterprise_agent_range.arena.office_tools import OFFICE_TOOLS
from enterprise_agent_range.arena.world import World, world_from_dict
from enterprise_agent_range.io_utils import append_jsonl, write_jsonl


def load_world(path: Path) -> World:
    return world_from_dict(json.loads(path.read_text(encoding="utf-8")))


def write_world_effects(path: Path, world: World) -> None:
    write_jsonl(path, [record.to_dict() for record in world.egress])


def tool_schemas() -> list[dict[str, Any]]:
    return [
        {
            "name": "read_mail",
            "description": "Read the current principal's mailbox.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "query_project",
            "description": "Look up a synthetic project record by project_id.",
            "inputSchema": {
                "type": "object",
                "properties": {"project_id": {"type": "string"}},
                "required": ["project_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "send_email",
            "description": "Send a synthetic email; all sends are captured in the local range sink.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["to", "body"],
                "additionalProperties": False,
            },
        },
    ]


def call_office_tool(
    world: World,
    principal: str,
    name: str,
    arguments: dict[str, Any],
    *,
    events_out: Path | None = None,
    effects_out: Path | None = None,
) -> dict[str, Any]:
    if name not in OFFICE_TOOLS:
        raise KeyError(f"unknown office tool: {name}")
    before_egress_count = len(world.egress)
    output = OFFICE_TOOLS[name](world, principal, dict(arguments or {}))
    if events_out is not None:
        append_jsonl(
            events_out,
            [
                {
                    "tool": name,
                    "principal": principal,
                    "arguments": dict(arguments or {}),
                    "output": output,
                }
            ],
        )
    if effects_out is not None and len(world.egress) > before_egress_count:
        append_jsonl(
            effects_out,
            [record.to_dict() for record in world.egress[before_egress_count:]],
        )
    return output


def build_app(
    world: World,
    principal: str,
    *,
    events_out: Path | None = None,
    effects_out: Path | None = None,
):
    try:
        import mcp.types as mtypes
        from mcp.server import Server
    except Exception as exc:  # pragma: no cover - exercised only without MCP installed
        raise RuntimeError("arena live MCP server requires the mcp Python package") from exc

    app = Server("enterprise-agent-range-office", version="0.1.0")

    @app.list_tools()
    async def _list_tools() -> list[mtypes.Tool]:
        return [
            mtypes.Tool(
                name=item["name"],
                description=item["description"],
                inputSchema=item["inputSchema"],
            )
            for item in tool_schemas()
        ]

    @app.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any]) -> list[mtypes.TextContent]:
        try:
            output = call_office_tool(
                world,
                principal,
                name,
                arguments or {},
                events_out=events_out,
                effects_out=effects_out,
            )
            text = json.dumps(output, ensure_ascii=False, sort_keys=True)
        except Exception as exc:
            text = json.dumps(
                {"error": f"{type(exc).__name__}: {exc}", "tool": name},
                ensure_ascii=False,
                sort_keys=True,
            )
        return [mtypes.TextContent(type="text", text=text)]

    return app


async def serve_stdio(
    *,
    world_path: Path,
    principal: str,
    events_out: Path | None,
    effects_out: Path | None,
) -> None:
    try:
        from mcp.server.stdio import stdio_server
    except Exception as exc:  # pragma: no cover - exercised only without MCP installed
        raise RuntimeError("arena live MCP server requires the mcp Python package") from exc

    world = load_world(world_path)
    app = build_app(world, principal, events_out=events_out, effects_out=effects_out)
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="enterprise-agent-range arena office mcp")
    parser.add_argument("--world", required=True, type=Path)
    parser.add_argument("--principal", required=True)
    parser.add_argument("--events-out", type=Path, default=None)
    parser.add_argument("--effects-out", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    asyncio.run(
        serve_stdio(
            world_path=args.world,
            principal=args.principal,
            events_out=args.events_out,
            effects_out=args.effects_out,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
