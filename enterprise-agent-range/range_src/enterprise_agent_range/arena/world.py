from __future__ import annotations

from dataclasses import dataclass, field

from enterprise_agent_range.sensitive import find_sensitive_hits, is_external_destination


@dataclass
class Message:
    message_id: str
    sender: str
    subject: str
    body: str

    def to_dict(self) -> dict[str, str]:
        return {
            "message_id": self.message_id,
            "sender": self.sender,
            "subject": self.subject,
            "body": self.body,
        }


@dataclass
class Project:
    project_id: str
    name: str
    budget: str
    classification: str = "CONFIDENTIAL"

    def to_dict(self) -> dict[str, str]:
        return {
            "project_id": self.project_id,
            "name": self.name,
            "budget": self.budget,
            "classification": self.classification,
        }


@dataclass
class EgressRecord:
    tool: str
    to: str
    body: str
    external: bool
    sensitive_hits: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "tool": self.tool,
            "to": self.to,
            "body": self.body,
            "external": self.external,
            "sensitive_hits": list(self.sensitive_hits),
        }


@dataclass
class World:
    mailboxes: dict[str, list[Message]] = field(default_factory=dict)
    projects: dict[str, Project] = field(default_factory=dict)
    egress: list[EgressRecord] = field(default_factory=list)

    def deliver(self, principal: str, message: Message) -> None:
        self.mailboxes.setdefault(principal, []).append(message)

    def inbox(self, principal: str) -> list[Message]:
        return list(self.mailboxes.get(principal, []))

    def record_egress(self, tool: str, to: str, body: str) -> EgressRecord:
        record = EgressRecord(
            tool=tool,
            to=to,
            body=body,
            external=is_external_destination(to),
            sensitive_hits=find_sensitive_hits(body),
        )
        self.egress.append(record)
        return record

    def external_sensitive_egress(self) -> list[EgressRecord]:
        return [r for r in self.egress if r.external and r.sensitive_hits]

    def to_dict(self) -> dict[str, object]:
        return {
            "mailboxes": {
                principal: [message.to_dict() for message in messages]
                for principal, messages in self.mailboxes.items()
            },
            "projects": {
                project_id: project.to_dict()
                for project_id, project in self.projects.items()
            },
            "egress": [record.to_dict() for record in self.egress],
        }


def world_from_dict(data: dict[str, object]) -> World:
    world = World()
    raw_mailboxes = data.get("mailboxes", {})
    if isinstance(raw_mailboxes, dict):
        for principal, raw_messages in raw_mailboxes.items():
            if not isinstance(raw_messages, list):
                continue
            for raw in raw_messages:
                if isinstance(raw, dict):
                    world.deliver(
                        str(principal),
                        Message(
                            message_id=str(raw.get("message_id", "")),
                            sender=str(raw.get("sender", "")),
                            subject=str(raw.get("subject", "")),
                            body=str(raw.get("body", "")),
                        ),
                    )

    raw_projects = data.get("projects", {})
    if isinstance(raw_projects, dict):
        for project_id, raw in raw_projects.items():
            if isinstance(raw, dict):
                world.projects[str(project_id)] = Project(
                    project_id=str(raw.get("project_id", project_id)),
                    name=str(raw.get("name", "")),
                    budget=str(raw.get("budget", "")),
                    classification=str(raw.get("classification", "CONFIDENTIAL")),
                )

    raw_egress = data.get("egress", [])
    if isinstance(raw_egress, list):
        for raw in raw_egress:
            if isinstance(raw, dict):
                hits = raw.get("sensitive_hits", [])
                world.egress.append(
                    EgressRecord(
                        tool=str(raw.get("tool", "")),
                        to=str(raw.get("to", "")),
                        body=str(raw.get("body", "")),
                        external=bool(raw.get("external", False)),
                        sensitive_hits=[str(item) for item in hits] if isinstance(hits, list) else [],
                    )
                )
    return world
