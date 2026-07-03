"""Registry of the ten P2 capabilities.

Single source of truth for what P2 covers. Each capability module exposes a
module-level ``SPEC``; this module aggregates them in the canonical order used by
the docs (docs/reference/p2-scope.md, P2 range).
"""

from __future__ import annotations

from typing import Any

from . import (
    benchmark,
    dashboard,
    discovery,
    evidence,
    identity,
    permissions,
    remediation,
    risk,
    scale,
    tenancy,
)
from .base import CapabilitySpec

CAPABILITIES: tuple[CapabilitySpec, ...] = (
    tenancy.SPEC,
    discovery.SPEC,
    identity.SPEC,
    permissions.SPEC,
    risk.SPEC,
    remediation.SPEC,
    scale.SPEC,
    benchmark.SPEC,
    evidence.SPEC,
    dashboard.SPEC,
)

_BY_KEY: dict[str, CapabilitySpec] = {spec.key: spec for spec in CAPABILITIES}


def capability_keys() -> tuple[str, ...]:
    """Return the capability keys in canonical order."""

    return tuple(spec.key for spec in CAPABILITIES)


def get_capability(key: str) -> CapabilitySpec:
    """Look up a capability spec by key. Raises ``KeyError`` if unknown."""

    return _BY_KEY[key]


def as_dicts() -> list[dict[str, Any]]:
    """Serialize the registry for CLI / report consumption."""

    return [spec.to_dict() for spec in CAPABILITIES]
