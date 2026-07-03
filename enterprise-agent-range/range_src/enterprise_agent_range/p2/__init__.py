"""P2 (research-grade) capability scaffolding for Enterprise Agent Range.

Skeleton only: interfaces, frozen data shapes, and a capability registry for the
ten P2 capabilities. Nothing in this package is wired into the P0/P1 runner,
oracle, or reports -- importing it has no effect on existing runs. See
``docs/reference/p2-scope.md``.

Every operation currently raises :class:`P2NotImplementedError`; each capability
gets its own spec -> plan -> implementation cycle later.
"""

from __future__ import annotations

from .base import (
    SCAFFOLD,
    CapabilitySpec,
    CapabilityStatus,
    P2NotImplementedError,
)
from .registry import CAPABILITIES, as_dicts, capability_keys, get_capability

__all__ = [
    "CAPABILITIES",
    "CapabilitySpec",
    "CapabilityStatus",
    "P2NotImplementedError",
    "SCAFFOLD",
    "as_dicts",
    "capability_keys",
    "get_capability",
]
