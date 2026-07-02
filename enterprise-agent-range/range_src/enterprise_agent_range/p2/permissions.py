"""P2 capability 4: JIT/JEA/JLA permission issuance (JIT/JEA/JLA 权限签发).

See docs/02-goals-and-scope.md (P2 range item 4) and
docs/13-implementation-roadmap.md (P2 item 4).

JIT = just-in-time, JEA = just-enough-access, JLA = just-long-enough-access.

Deterministic implementation: no ``datetime.now()``/``time.time()``. Callers
inject the current time as an integer epoch-seconds parameter.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from typing import Any

from .base import CapabilitySpec, CapabilityStatus


@dataclass(frozen=True)
class GrantRequest:
    """A request for a scoped, time-bounded capability grant."""

    principal_id: str
    capability: str
    scope: tuple[str, ...] = ()  # just-enough-access: minimal resource scope
    ttl_seconds: int = 0  # just-long-enough-access
    justification: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IssuedGrant:
    """A grant issued in response to a request, with expiry bookkeeping.

    ``issued_at``/``expires_at`` are integer epoch seconds (deterministic;
    never derived from a wall-clock read inside this module).
    """

    grant_id: str
    request: GrantRequest
    issued_at: int = 0
    expires_at: int = 0
    revoked: bool = False


def _serialize_for_grant_id(request: GrantRequest, now_epoch: int) -> str:
    """Stable JSON serialization of a request + issue time, used only to
    derive a deterministic grant_id (same inputs -> same grant_id).
    """

    payload = {
        "principal_id": request.principal_id,
        "capability": request.capability,
        "scope": list(request.scope),
        "ttl_seconds": request.ttl_seconds,
        "justification": request.justification,
        "metadata": request.metadata,
        "now_epoch": now_epoch,
    }
    return json.dumps(payload, sort_keys=True, default=str)


def _grant_id(request: GrantRequest, now_epoch: int) -> str:
    digest = hashlib.sha256(_serialize_for_grant_id(request, now_epoch).encode("utf-8")).hexdigest()
    return f"grant-{digest[:16]}"


class GrantAuthority:
    """Issues, checks, and revokes JIT/JEA/JLA grants.

    Planned oracle fields: ``jit_grant_scoped``, ``jit_grant_expired``,
    ``grant_reuse_after_expiry_blocked`` (not yet wired into ``oracles.py``).
    """

    def issue(self, request: GrantRequest, now_epoch: int) -> IssuedGrant:
        """Issue a grant for ``request`` as of ``now_epoch`` (int epoch seconds).

        ``grant_id`` is deterministic: a stable hash of the request contents
        and ``now_epoch``, so identical inputs always yield the identical
        grant_id. ``expires_at = now_epoch + request.ttl_seconds``.
        """

        return IssuedGrant(
            grant_id=_grant_id(request, now_epoch),
            request=request,
            issued_at=now_epoch,
            expires_at=now_epoch + request.ttl_seconds,
            revoked=False,
        )

    def check(
        self,
        grant: IssuedGrant,
        capability: str,
        scope_needed: tuple[str, ...],
        when_epoch: int,
    ) -> bool:
        """True iff the grant authorizes ``capability``/``scope_needed`` at ``when_epoch``.

        All five conditions must hold:
        - not revoked
        - ``grant.issued_at <= when_epoch < grant.expires_at`` (JLA: active window)
        - ``capability == grant.request.capability`` (exact capability match)
        - ``set(scope_needed) <= set(grant.request.scope)`` (JEA: no over-scoping)
        """

        if grant.revoked:
            return False
        if when_epoch < grant.issued_at:
            return False
        if when_epoch >= grant.expires_at:
            return False
        if capability != grant.request.capability:
            return False
        if not set(scope_needed).issubset(set(grant.request.scope)):
            return False
        return True

    def revoke(self, grant: IssuedGrant) -> IssuedGrant:
        """Return a NEW ``IssuedGrant`` with ``revoked=True``."""

        return replace(grant, revoked=True)


SPEC = CapabilitySpec(
    key="permissions",
    title="JIT/JEA/JLA 权限签发 / just-in-time permission issuance",
    module=__name__,
    roadmap_refs=("docs/02-goals-and-scope.md#P2-4", "docs/13-implementation-roadmap.md#P2-4"),
    summary="Issue scoped, time-bounded grants and reject over-scoped or expired reuse.",
    status=CapabilityStatus.IMPLEMENTED,
    planned_expected_fields=(
        "jit_grant_scoped",
        "jit_grant_expired",
        "grant_reuse_after_expiry_blocked",
    ),
    planned_metrics=("expired_grant_bypass_rate",),
)
