"""P2 capability 1: multi-tenant enterprises (多租户企业).

Scaffold only. See docs/02-goals-and-scope.md (P2 range item 1) and
docs/13-implementation-roadmap.md (P2 item 1). Nothing here is wired into the
P0/P1 runner, oracle, or reports yet; this module fixes the data shapes and the
interface so a future implementation slots in without touching P1.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .base import SCAFFOLD, CapabilitySpec, P2NotImplementedError


@dataclass(frozen=True)
class Tenant:
    """A synthetic isolated enterprise tenant within the range."""

    tenant_id: str
    display_name: str
    data_residency: str = "range-local"  # synthetic region label, never real infra
    metadata: dict[str, Any] = field(default_factory=dict)


class TenantRegistry:
    """Interface for registering tenants and enforcing per-tenant isolation.

    Planned oracle fields: ``tenant_isolation_enforced``,
    ``cross_tenant_access_blocked``. A future implementation will scope
    ``RangeState`` side-effect/audit sinks per tenant so that cross-tenant reads
    or writes are detectable.
    """

    def register(self, tenant: Tenant) -> None:  # noqa: D401 - scaffold stub
        raise P2NotImplementedError("p2.tenancy.TenantRegistry.register is a scaffold stub")

    def isolate(self, tenant_id: str, state: Any) -> Any:
        raise P2NotImplementedError("p2.tenancy.TenantRegistry.isolate is a scaffold stub")


SPEC = CapabilitySpec(
    key="tenancy",
    title="多租户企业 / multi-tenant enterprises",
    module=__name__,
    roadmap_refs=("docs/02-goals-and-scope.md#P2-1", "docs/13-implementation-roadmap.md#P2-1"),
    summary="Isolate range state, sinks, and evidence per synthetic enterprise tenant.",
    status=SCAFFOLD,
    planned_expected_fields=("tenant_isolation_enforced", "cross_tenant_access_blocked"),
    planned_metrics=("cross_tenant_leak_rate",),
)
