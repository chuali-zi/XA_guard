"""Small immutable models shared by the control API, store, and worker."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Principal:
    subject: str
    username: str
    tenant_id: str
    agent_id: str
    issuer: str
    token_id_hash: str
    roles: tuple[str, ...] = ()
    groups: tuple[str, ...] = ()
    scopes: tuple[str, ...] = ()

    def has_role(self, role: str) -> bool:
        return role in self.roles


@dataclass(frozen=True)
class Assignment:
    assignment_id: str
    tenant_id: str
    subject_type: str
    subject_id: str
    agent_id: str
    tools: tuple[str, ...]
    data_domains: tuple[str, ...]
    valid_from: str
    valid_until: str | None
    version: int
    changed_by: str


@dataclass(frozen=True)
class EffectContractV2:
    tool_name: str
    contract_version: str
    contract_hash: str
    success_pointer: str
    success_equals: Any
    side_effect_level: str
    reversibility: str
    undo_window_seconds: int
    recovery_fields: dict[str, str] = field(default_factory=dict)
    compensation_tool: str = ""
    compensation_arguments: dict[str, Any] = field(default_factory=dict)
    idempotency_header: str = "Idempotency-Key"
    reconciliation_method: str = ""
    retry_delays_seconds: tuple[int, ...] = (5, 30, 120)

