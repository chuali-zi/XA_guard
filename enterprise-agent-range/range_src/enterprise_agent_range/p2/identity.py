"""P2 capability 3: agent identity lifecycle (Agent 身份生命周期).

Scaffold only. See docs/02-goals-and-scope.md (P2 range item 3) and
docs/13-implementation-roadmap.md (P2 item 3). No runtime wiring yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .base import SCAFFOLD, CapabilitySpec, P2NotImplementedError


class IdentityState:
    """Lifecycle states an agent identity can move through."""

    PROVISIONED = "provisioned"
    ACTIVE = "active"
    ROTATED = "rotated"
    SUSPENDED = "suspended"
    REVOKED = "revoked"
    RETIRED = "retired"
    ALL = (PROVISIONED, ACTIVE, ROTATED, SUSPENDED, REVOKED, RETIRED)


@dataclass(frozen=True)
class AgentIdentity:
    """A managed agent identity with a lifecycle state and synthetic credentials."""

    agent_id: str
    state: str = IdentityState.PROVISIONED
    credential_ref: str = "range-cred-placeholder"  # synthetic, never a real secret
    metadata: dict[str, Any] = field(default_factory=dict)


class IdentityLifecycle:
    """Interface for provisioning, rotating, and revoking agent identities.

    Planned oracle fields: ``identity_state_valid``,
    ``revoked_identity_action_blocked``. A future implementation will enforce
    that revoked/retired identities cannot drive tool calls.
    """

    def transition(self, identity: AgentIdentity, to_state: str) -> AgentIdentity:
        raise P2NotImplementedError("p2.identity.IdentityLifecycle.transition is a scaffold stub")


SPEC = CapabilitySpec(
    key="identity",
    title="Agent 身份生命周期 / agent identity lifecycle",
    module=__name__,
    roadmap_refs=("docs/02-goals-and-scope.md#P2-3", "docs/13-implementation-roadmap.md#P2-3"),
    summary="Model provision/rotate/suspend/revoke/retire states and enforce them on tool use.",
    status=SCAFFOLD,
    planned_expected_fields=("identity_state_valid", "revoked_identity_action_blocked"),
    planned_metrics=("revoked_identity_bypass_rate",),
)
