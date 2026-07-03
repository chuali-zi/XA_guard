"""P2 capability 3: agent identity lifecycle (Agent 身份生命周期).

See docs/reference/p2-scope.md (P2 range item 3) and
docs/reference/p2-scope.md (P2 item 3).

Implements a deterministic state machine over :class:`IdentityState`. No
runtime wiring into ``oracles.py`` yet (see ``planned_expected_fields`` on
``SPEC``); this module is independently testable via plain dataclasses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any

from .base import CapabilitySpec, CapabilityStatus

_ROTATION_SUFFIX_RE = re.compile(r"-r(\d+)$")


class IdentityState:
    """Lifecycle states an agent identity can move through."""

    PROVISIONED = "provisioned"
    ACTIVE = "active"
    ROTATED = "rotated"
    SUSPENDED = "suspended"
    REVOKED = "revoked"
    RETIRED = "retired"
    ALL = (PROVISIONED, ACTIVE, ROTATED, SUSPENDED, REVOKED, RETIRED)


# Explicit allow-list of legal transitions. Anything not listed here is
# illegal and `IdentityLifecycle.transition` raises ValueError for it.
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    IdentityState.PROVISIONED: frozenset({IdentityState.ACTIVE}),
    IdentityState.ACTIVE: frozenset(
        {
            IdentityState.ROTATED,
            IdentityState.SUSPENDED,
            IdentityState.REVOKED,
            IdentityState.RETIRED,
        }
    ),
    IdentityState.ROTATED: frozenset(
        {
            IdentityState.ACTIVE,
            IdentityState.SUSPENDED,
            IdentityState.REVOKED,
            IdentityState.RETIRED,
        }
    ),
    IdentityState.SUSPENDED: frozenset(
        {IdentityState.ACTIVE, IdentityState.REVOKED, IdentityState.RETIRED}
    ),
    IdentityState.REVOKED: frozenset({IdentityState.RETIRED}),
    IdentityState.RETIRED: frozenset(),  # terminal state
}

# States in which an identity is allowed to drive tool calls. This is the
# security-relevant gate: revoked/suspended/retired/provisioned identities
# must never be able to act.
ACTIONABLE_STATES: frozenset[str] = frozenset({IdentityState.ACTIVE, IdentityState.ROTATED})


@dataclass(frozen=True)
class AgentIdentity:
    """A managed agent identity with a lifecycle state and synthetic credentials."""

    agent_id: str
    state: str = IdentityState.PROVISIONED
    credential_ref: str = "range-cred-placeholder"  # synthetic, never a real secret
    metadata: dict[str, Any] = field(default_factory=dict)


def _rotate_credential_ref(current: str) -> str:
    """Deterministically derive a new credential_ref by bumping a stable
    trailing ``-rN`` counter suffix (appending ``-r1`` if none is present).
    """

    match = _ROTATION_SUFFIX_RE.search(current)
    if match:
        base = current[: match.start()]
        counter = int(match.group(1)) + 1
    else:
        base = current
        counter = 1
    return f"{base}-r{counter}"


class IdentityLifecycle:
    """Provisions, rotates, suspends, revokes, and retires agent identities.

    Planned oracle fields: ``identity_state_valid``,
    ``revoked_identity_action_blocked`` (not yet wired into ``oracles.py``).
    """

    def transition(self, identity: AgentIdentity, to_state: str) -> AgentIdentity:
        """Return a NEW ``AgentIdentity`` moved to ``to_state``.

        Raises ``ValueError`` if ``to_state`` is not a known state, or if the
        transition from ``identity.state`` to ``to_state`` is not allowed.
        On rotation, also derives a new deterministic ``credential_ref``.
        """

        if to_state not in IdentityState.ALL:
            raise ValueError(f"unknown identity state: {to_state!r}")

        allowed = ALLOWED_TRANSITIONS.get(identity.state, frozenset())
        if to_state not in allowed:
            raise ValueError(
                f"illegal identity transition: {identity.state!r} -> {to_state!r}"
            )

        if to_state == IdentityState.ROTATED:
            new_credential_ref = _rotate_credential_ref(identity.credential_ref)
            return replace(identity, state=to_state, credential_ref=new_credential_ref)

        return replace(identity, state=to_state)

    def can_act(self, identity: AgentIdentity) -> bool:
        """True only when the identity is in an actionable state.

        Security-relevant gate: identities that are provisioned (not yet
        activated), suspended, revoked, or retired must not be able to drive
        tool calls.
        """

        return identity.state in ACTIONABLE_STATES


class IdentityRegistry:
    """Small in-memory registry of ``AgentIdentity`` objects keyed by agent_id."""

    def __init__(self) -> None:
        self._by_agent_id: dict[str, AgentIdentity] = {}

    def register(self, identity: AgentIdentity) -> AgentIdentity:
        """Store (or overwrite) an identity, returning it for chaining."""

        self._by_agent_id[identity.agent_id] = identity
        return identity

    def get(self, agent_id: str) -> AgentIdentity:
        """Look up an identity by agent_id. Raises ``KeyError`` if unknown."""

        return self._by_agent_id[agent_id]

    def list(self) -> tuple[AgentIdentity, ...]:
        """Return all registered identities in registration order."""

        return tuple(self._by_agent_id.values())


SPEC = CapabilitySpec(
    key="identity",
    title="Agent 身份生命周期 / agent identity lifecycle",
    module=__name__,
    roadmap_refs=("docs/reference/p2-scope.md#P2-3", "docs/reference/p2-scope.md#P2-3"),
    summary="Model provision/rotate/suspend/revoke/retire states and enforce them on tool use.",
    status=CapabilityStatus.IMPLEMENTED,
    planned_expected_fields=("identity_state_valid", "revoked_identity_action_blocked"),
    planned_metrics=("revoked_identity_bypass_rate",),
)
