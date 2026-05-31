"""Toy FastMCP server for testing MCP elicitation HITL approval.

Run manually with an MCP client that supports elicitation:
    python -m demo.elicitation_probe_server

Then call tool:
    dangerous_echo({"payload": "hello"})
"""
from __future__ import annotations

from mcp.server.fastmcp import Context, FastMCP
from pydantic import BaseModel, Field


app = FastMCP("xa-guard-elicitation-probe")


class ApprovalForm(BaseModel):
    approve: bool = Field(description="Approve this toy high-risk action")
    reason: str = Field(default="", description="Optional approval reason")


@app.tool()
async def dangerous_echo(payload: str, ctx: Context) -> str:
    """Ask for HITL approval, then echo the payload only if approved."""
    result = await ctx.elicit(
        message=(
            "XA-Guard toy HITL probe: approve dangerous_echo?\n"
            f"payload={payload}"
        ),
        schema=ApprovalForm,
    )
    if result.action != "accept" or not result.data.approve:
        return "rejected"
    return f"approved: {payload}"


if __name__ == "__main__":
    app.run("stdio")
