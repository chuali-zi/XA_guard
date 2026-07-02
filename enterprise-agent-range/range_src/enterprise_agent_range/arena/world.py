from __future__ import annotations

from dataclasses import dataclass, field

from enterprise_agent_range.sensitive import find_sensitive_hits, is_external_destination


@dataclass
class Message:
    message_id: str
    sender: str
    subject: str
    body: str


@dataclass
class Project:
    project_id: str
    name: str
    budget: str
    classification: str = "CONFIDENTIAL"


@dataclass
class EgressRecord:
    tool: str
    to: str
    body: str
    external: bool
    sensitive_hits: list[str]


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
