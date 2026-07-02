"""P2 capability 9: third-party TSA/HSM evidence chain (第三方 TSA/HSM 证据链对接).

Scaffold only. See docs/02-goals-and-scope.md (P2 range item 9) and
docs/13-implementation-roadmap.md (P2 item 9). No runtime wiring yet.

TSA = time-stamping authority, HSM = hardware security module. The scaffold
targets an offline/mock interface only; no real TSA/HSM is contacted and no real
keys are used.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .base import SCAFFOLD, CapabilitySpec, P2NotImplementedError


@dataclass(frozen=True)
class TimestampToken:
    """A (mock) RFC-3161-style timestamp token over an evidence hash."""

    evidence_hash: str
    authority: str = "mock-tsa"
    timestamp: str = ""  # ISO-8601 in a future implementation
    token_ref: str = ""  # opaque handle to a synthetic token blob


class TimestampAuthority:
    """Interface for obtaining and verifying timestamp tokens.

    Planned oracle fields: ``tsa_timestamp_valid``, ``evidence_countersigned``.
    """

    def stamp(self, evidence_hash: str) -> TimestampToken:
        raise P2NotImplementedError("p2.evidence.TimestampAuthority.stamp is a scaffold stub")

    def verify(self, token: TimestampToken) -> bool:
        raise P2NotImplementedError("p2.evidence.TimestampAuthority.verify is a scaffold stub")


class HsmSigner:
    """Interface for signing evidence manifests with a (mock) HSM-held key."""

    def sign(self, payload: bytes) -> dict[str, Any]:
        raise P2NotImplementedError("p2.evidence.HsmSigner.sign is a scaffold stub")


SPEC = CapabilitySpec(
    key="evidence",
    title="TSA/HSM 证据链 / third-party timestamp & HSM evidence",
    module=__name__,
    roadmap_refs=("docs/02-goals-and-scope.md#P2-9", "docs/13-implementation-roadmap.md#P2-9"),
    summary="Countersign and timestamp evidence bundles via a mock TSA/HSM interface (offline).",
    status=SCAFFOLD,
    planned_expected_fields=("tsa_timestamp_valid", "evidence_countersigned"),
    planned_metrics=("countersigned_evidence_rate",),
)
