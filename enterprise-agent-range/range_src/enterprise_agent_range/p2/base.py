from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class CapabilityStatus:
    """Lifecycle status for a P2 capability scaffold.

    Every capability starts at ``SCAFFOLD``. As real implementations land, the
    module owner flips the module-level ``SPEC.status`` to ``IN_PROGRESS`` and
    finally ``IMPLEMENTED``.
    """

    SCAFFOLD = "scaffold"
    IN_PROGRESS = "in_progress"
    IMPLEMENTED = "implemented"
    ALL = (SCAFFOLD, IN_PROGRESS, IMPLEMENTED)


# Convenience alias for the common case.
SCAFFOLD = CapabilityStatus.SCAFFOLD


class P2NotImplementedError(NotImplementedError):
    """Raised by P2 scaffold stubs that have no implementation yet.

    A dedicated subclass lets tests lock the "still a stub" contract precisely
    and lets future implementers grep for every remaining stub.
    """


@dataclass(frozen=True)
class CapabilitySpec:
    """Registry entry describing one P2 capability and its planned surface.

    ``planned_expected_fields`` / ``planned_metrics`` document the oracle and
    metrics surface a future implementation will add. They are intentionally NOT
    wired into ``oracles.py`` in the scaffold phase.
    """

    key: str
    title: str
    module: str
    roadmap_refs: tuple[str, ...]
    summary: str
    status: str = SCAFFOLD
    planned_expected_fields: tuple[str, ...] = field(default_factory=tuple)
    planned_metrics: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "module": self.module,
            "roadmap_refs": list(self.roadmap_refs),
            "summary": self.summary,
            "status": self.status,
            "planned_expected_fields": list(self.planned_expected_fields),
            "planned_metrics": list(self.planned_metrics),
        }
