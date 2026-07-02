"""P2 capability 4: JIT/JEA/JLA permission issuance (JIT/JEA/JLA 权限签发).

Scaffold only. See docs/02-goals-and-scope.md (P2 range item 4) and
docs/13-implementation-roadmap.md (P2 item 4). No runtime wiring yet.

JIT = just-in-time, JEA = just-enough-access, JLA = just-long-enough-access.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .base import SCAFFOLD, CapabilitySpec, P2NotImplementedError


@dataclass(frozen=True)
class GrantRequest:
    """A request for a scoped, time-bounded capability grant."""

    principal_id: str
    capability: str
    scope: tuple[str, ...] = ()  # just-enough-access: minimal resource scope
    ttl_seconds: int = 0  # just-long-enough-access: 0 means unset in scaffold
    justification: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IssuedGrant:
    """A grant issued in response to a request, with expiry bookkeeping."""

    grant_id: str
    request: GrantRequest
    issued_at: str = ""  # ISO-8601 in a future implementation
    expires_at: str = ""
    revoked: bool = False


class GrantAuthority:
    """Interface for issuing, checking, and expiring JIT grants.

    Planned oracle fields: ``jit_grant_scoped``, ``jit_grant_expired``,
    ``grant_reuse_after_expiry_blocked``. A future implementation will bind a
    grant to a single trace and reject reuse past ``expires_at``.
    """

    def issue(self, request: GrantRequest) -> IssuedGrant:
        raise P2NotImplementedError("p2.permissions.GrantAuthority.issue is a scaffold stub")

    def check(self, grant: IssuedGrant, capability: str, when: str) -> bool:
        raise P2NotImplementedError("p2.permissions.GrantAuthority.check is a scaffold stub")


SPEC = CapabilitySpec(
    key="permissions",
    title="JIT/JEA/JLA 权限签发 / just-in-time permission issuance",
    module=__name__,
    roadmap_refs=("docs/02-goals-and-scope.md#P2-4", "docs/13-implementation-roadmap.md#P2-4"),
    summary="Issue scoped, time-bounded grants and reject over-scoped or expired reuse.",
    status=SCAFFOLD,
    planned_expected_fields=(
        "jit_grant_scoped",
        "jit_grant_expired",
        "grant_reuse_after_expiry_blocked",
    ),
    planned_metrics=("expired_grant_bypass_rate",),
)
