"""P2 capability 1: multi-tenant enterprises (多租户企业).

Implements a deterministic, synthetic per-tenant registry plus isolation and
cross-tenant leak-detection helpers over plain dict rows. See
docs/02-goals-and-scope.md (P2 range item 1) and
docs/13-implementation-roadmap.md (P2 item 1). This module still does not wire
into the P0/P1 runner, oracle, or reports; it only fixes deterministic,
duck-typed data shapes and behavior so a future runner integration can plug
in without touching P1.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .base import CapabilityStatus, CapabilitySpec


@dataclass(frozen=True)
class Tenant:
    """A synthetic isolated enterprise tenant within the range."""

    tenant_id: str
    display_name: str
    data_residency: str = "range-local"  # synthetic region label, never real infra
    metadata: dict[str, Any] = field(default_factory=dict)


class TenantRegistry:
    """Registers tenants and enforces per-tenant isolation over plain dict rows.

    Rows are plain ``dict`` objects carrying a ``"tenant_id"`` key (e.g. audit
    log entries or side-effect records fed in by a future runner
    integration). ``isolate`` produces a per-tenant view of a row list;
    ``cross_tenant_violations`` flags rows that leaked across the tenant
    boundary (a foreign or missing ``tenant_id``). Maps to the planned oracle
    fields ``tenant_isolation_enforced`` and ``cross_tenant_access_blocked``.
    """

    def __init__(self) -> None:
        self._tenants: dict[str, Tenant] = {}

    def register(self, tenant: Tenant) -> None:
        """Register a new tenant.

        Raises ``ValueError`` if ``tenant.tenant_id`` is already registered.
        """
        if tenant.tenant_id in self._tenants:
            raise ValueError(f"tenant already registered: {tenant.tenant_id!r}")
        self._tenants[tenant.tenant_id] = tenant

    def get(self, tenant_id: str) -> Tenant:
        """Look up a registered tenant. Raises ``KeyError`` if missing."""
        try:
            return self._tenants[tenant_id]
        except KeyError:
            raise KeyError(f"unknown tenant: {tenant_id!r}") from None

    def list_tenants(self) -> list[Tenant]:
        """Return all registered tenants sorted deterministically by tenant_id."""
        return [self._tenants[key] for key in sorted(self._tenants)]

    @staticmethod
    def isolate(tenant_id: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return the subset of ``rows`` belonging to ``tenant_id``.

        Input order is preserved. This is the per-tenant "view" a future
        runner integration would hand to a tenant-scoped agent.
        """
        return [row for row in rows if row.get("tenant_id") == tenant_id]

    @staticmethod
    def cross_tenant_violations(tenant_id: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return rows that leaked into ``tenant_id``'s view.

        A row is a violation if its ``tenant_id`` differs from the expected
        tenant, or if it is missing a ``tenant_id`` entirely. Input order is
        preserved.
        """
        return [row for row in rows if row.get("tenant_id") != tenant_id]


SPEC = CapabilitySpec(
    key="tenancy",
    title="多租户企业 / multi-tenant enterprises",
    module=__name__,
    roadmap_refs=("docs/02-goals-and-scope.md#P2-1", "docs/13-implementation-roadmap.md#P2-1"),
    summary="Isolate range state, sinks, and evidence per synthetic enterprise tenant.",
    status=CapabilityStatus.IMPLEMENTED,
    planned_expected_fields=("tenant_isolation_enforced", "cross_tenant_access_blocked"),
    planned_metrics=("cross_tenant_leak_rate",),
)
