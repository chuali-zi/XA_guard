from __future__ import annotations

from typing import Any, Callable

from enterprise_agent_range.arena.world import World

ToolFn = Callable[[World, str, dict[str, Any]], dict[str, Any]]


def read_mail(world: World, principal: str, args: dict[str, Any]) -> dict[str, Any]:
    return {
        "messages": [
            {"message_id": m.message_id, "sender": m.sender, "subject": m.subject, "body": m.body}
            for m in world.inbox(principal)
        ]
    }


def query_project(world: World, principal: str, args: dict[str, Any]) -> dict[str, Any]:
    project = world.projects.get(str(args.get("project_id", "")))
    if project is None:
        return {"found": False, "project_id": args.get("project_id", "")}
    return {
        "found": True,
        "project_id": project.project_id,
        "name": project.name,
        "budget": project.budget,
        "classification": project.classification,
    }


def send_email(world: World, principal: str, args: dict[str, Any]) -> dict[str, Any]:
    record = world.record_egress("send_email", str(args.get("to", "")), str(args.get("body", "")))
    return {
        "sent": True,
        "to": record.to,
        "external": record.external,
        "sensitive_hits": record.sensitive_hits,
    }


OFFICE_TOOLS: dict[str, ToolFn] = {
    "read_mail": read_mail,
    "query_project": query_project,
    "send_email": send_email,
}
