"""Static governance YAML is an immutable maximum authorization ceiling."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from xa_guard.governance import GovernanceRegistry


class CeilingError(RuntimeError):
    pass


@dataclass(frozen=True)
class AgentCeiling:
    agent_id: str
    tenant_id: str
    name: str
    purpose: str
    tools: tuple[str, ...]
    data_domains: tuple[str, ...]


class GovernanceCeiling:
    def __init__(self, path: str | Path) -> None:
        registry = GovernanceRegistry.from_yaml(path)
        self.registry_version = registry.registry_version
        self.agents = {
            agent.agent_id: AgentCeiling(
                agent_id=agent.agent_id,
                tenant_id=agent.tenant_id,
                name=agent.name,
                purpose=agent.purpose,
                tools=tuple(agent.allowed_tools),
                data_domains=tuple(agent.allowed_data_domains),
            )
            for agent in registry.agents.values()
            if agent.active
        }

    def validate_assignment(self, tenant_id: str, value: dict[str, Any]) -> AgentCeiling:
        agent = self.agents.get(str(value.get("agent_id") or ""))
        if agent is None or agent.tenant_id != tenant_id:
            raise CeilingError("agent is absent, disabled, or belongs to another tenant")
        tools = {str(v) for v in value.get("tools") or []}
        domains = {str(v) for v in value.get("data_domains") or []}
        if not tools or not domains:
            raise CeilingError("assignment tools and data_domains must be non-empty")
        if not tools.issubset(set(agent.tools)):
            raise CeilingError("assignment exceeds the agent tool ceiling")
        if not domains.issubset(set(agent.data_domains)):
            raise CeilingError("assignment exceeds the agent data-domain ceiling")
        if value.get("subject_type") not in {"human", "group"} or not str(value.get("subject_id") or ""):
            raise CeilingError("assignment subject is invalid")
        return agent

