"""Planned P2 schema surface (documentation only, NOT enforced).

These names describe the ``expected`` fields, metrics, and case fields a future
P2 implementation will add. They are intentionally kept out of
``oracles.SUPPORTED_EXPECTED_FIELDS`` and out of manifest validation during the
scaffold phase, so P0/P1 runs and validation are unaffected.

The per-capability field lists are derived from each ``CapabilitySpec`` to keep a
single source of truth.
"""

from __future__ import annotations

from .registry import CAPABILITIES

# Top-level case fields P2 cases are expected to introduce (not yet validated).
PLANNED_CASE_FIELDS: tuple[str, ...] = (
    "tenant_id",
    "identity_state",
    "grant_request",
    "risk_budget",
    "benchmark_source",
)


def planned_expected_fields() -> dict[str, tuple[str, ...]]:
    """Map capability key -> planned oracle ``expected`` fields."""

    return {spec.key: spec.planned_expected_fields for spec in CAPABILITIES}


def planned_metrics() -> dict[str, tuple[str, ...]]:
    """Map capability key -> planned metrics keys."""

    return {spec.key: spec.planned_metrics for spec in CAPABILITIES}


def all_planned_expected_fields() -> tuple[str, ...]:
    """Flat, sorted, de-duplicated set of every planned ``expected`` field."""

    names: set[str] = set()
    for fields in planned_expected_fields().values():
        names.update(fields)
    return tuple(sorted(names))
