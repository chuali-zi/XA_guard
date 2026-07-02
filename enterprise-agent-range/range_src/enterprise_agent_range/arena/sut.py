from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from enterprise_agent_range.arena.office_tools import OFFICE_TOOLS
from enterprise_agent_range.arena.world import World
from enterprise_agent_range.sensitive import find_sensitive_hits, is_external_destination


@dataclass
class ToolCall:
    tool: str
    args: dict[str, Any]


@dataclass
class AuditRecord:
    tool: str
    decision: str
    reason: str


class SUT:
    sut_id: str = "sut"

    def __init__(self) -> None:
        self.audit: list[AuditRecord] = []

    def decide(self, principal: str, call: ToolCall) -> tuple[str, str]:
        raise NotImplementedError

    def invoke(self, world: World, principal: str, call: ToolCall) -> dict[str, Any]:
        decision, reason = self.decide(principal, call)
        self.audit.append(AuditRecord(tool=call.tool, decision=decision, reason=reason))
        if decision == "deny":
            return {"decision": "deny", "reason": reason, "executed": False}
        output = OFFICE_TOOLS[call.tool](world, principal, dict(call.args))
        output["decision"] = "allow"
        output["executed"] = True
        return output


class NullSUT(SUT):
    sut_id = "null-passthrough"

    def decide(self, principal: str, call: ToolCall) -> tuple[str, str]:
        return "allow", "null passthrough executes everything"


class GuardStubSUT(SUT):
    """Deterministic policy double: blocks external egress carrying sensitive data."""

    sut_id = "guard-stub"

    def decide(self, principal: str, call: ToolCall) -> tuple[str, str]:
        if call.tool == "send_email":
            to = str(call.args.get("to", ""))
            body = str(call.args.get("body", ""))
            if is_external_destination(to) and find_sensitive_hits(body):
                return "deny", "external egress of sensitive data blocked"
        return "allow", "no policy violation"
