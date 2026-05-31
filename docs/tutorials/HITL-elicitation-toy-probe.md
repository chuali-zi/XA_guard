# HITL elicitation toy probe

This is a minimal MCP elicitation probe for XA-Guard Gate 2 experiments.

## What it proves

- `demo/elicitation_probe_server.py` is a FastMCP stdio server that calls `Context.elicit`.
- `scripts/probe_mcp_elicitation.py` starts that server with `mcp.ClientSession` and an automated `elicitation_callback`.
- A successful probe proves the local MCP protocol path works with `mcp` and FastMCP. It does not prove that Cursor, Claude Code, Codex, Trae, CodeBuddy, Qoder CN, or another IDE rendered a real interactive popup.

## Local automated probe

Approve path:

```powershell
python scripts/probe_mcp_elicitation.py
```

Reject path:

```powershell
python scripts/probe_mcp_elicitation.py --reject
```

Expected signals:

- `elicitation_events` contains one event.
- approve path returns `approved: hello`.
- reject path returns `rejected`.

## Manual IDE/client popup test

Register this stdio server in a client that explicitly supports MCP elicitation:

```json
{
  "mcpServers": {
    "xa-guard-elicitation-probe": {
      "command": "python",
      "args": ["-m", "demo.elicitation_probe_server"],
      "cwd": "D:\\race\\jiebang"
    }
  }
}
```

Then call `dangerous_echo` with:

```json
{"payload": "hello"}
```

Record as a real popup test only if the client displays an interactive elicitation approval UI and the approved call returns `approved: hello`.

## Domestic client fallback wording

Trae, CodeBuddy, Qoder CN, and similar domestic IDE clients should remain documented as "elicitation not publicly declared / requires version-specific testing" until an actual client popup run is recorded. If no elicitation capability is declared, XA-Guard must keep the text/stdout fallback path rather than marking full HITL popup support.
