"""P2 capability 9: third-party TSA/HSM evidence chain (第三方 TSA/HSM 证据链对接).

Implements a deterministic, fully offline mock of a TSA (time-stamping
authority) and an HSM (hardware security module) signer. Both use HMAC-SHA256
over module-level mock keys — there is no real TSA/HSM involved and the keys
are obviously-fake placeholders, never production secrets.

See docs/reference/p2-scope.md (P2 range item 9) and
docs/reference/p2-scope.md (P2 item 9).
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any

from .base import CapabilityStatus, CapabilitySpec

# Obviously-fake mock keys. Never real TSA/HSM key material.
_MOCK_TSA_KEY = b"range-mock-tsa-key"
_MOCK_HSM_KEY = b"range-mock-hsm-key"


@dataclass(frozen=True)
class TimestampToken:
    """A (mock) RFC-3161-style timestamp token over an evidence hash."""

    evidence_hash: str
    authority: str = "mock-tsa"
    timestamp: str = ""  # caller-supplied, e.g. ISO-8601
    token_ref: str = ""  # HMAC-SHA256(evidence_hash|timestamp) hex digest


class TimestampAuthority:
    """Offline mock TSA: deterministic HMAC-based "timestamp" tokens.

    Not a real TSA. ``stamp`` is deterministic given the same
    ``(evidence_hash, at)`` pair, and ``verify`` recomputes the HMAC to detect
    tampering with either the evidence hash or the timestamp.
    """

    def stamp(self, evidence_hash: str, at: str) -> TimestampToken:
        token_ref = hmac.new(
            _MOCK_TSA_KEY,
            f"{evidence_hash}|{at}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return TimestampToken(
            evidence_hash=evidence_hash,
            authority="mock-tsa",
            timestamp=at,
            token_ref=token_ref,
        )

    def verify(self, token: TimestampToken) -> bool:
        expected = hmac.new(
            _MOCK_TSA_KEY,
            f"{token.evidence_hash}|{token.timestamp}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, token.token_ref)


class HsmSigner:
    """Offline mock HSM signer: deterministic HMAC-SHA256 over a payload.

    Not a real HSM. ``sign`` is deterministic for a given payload and
    ``verify`` recomputes the HMAC using constant-time comparison.
    """

    def sign(self, payload: bytes) -> dict[str, Any]:
        signature = hmac.new(_MOCK_HSM_KEY, payload, hashlib.sha256).hexdigest()
        return {
            "algo": "HMAC-SHA256(mock-hsm)",
            "key_id": "mock-hsm-key",
            "signature": signature,
        }

    def verify(self, payload: bytes, signature: str) -> bool:
        expected = hmac.new(_MOCK_HSM_KEY, payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)


SPEC = CapabilitySpec(
    key="evidence",
    title="TSA/HSM 证据链 / third-party timestamp & HSM evidence",
    module=__name__,
    roadmap_refs=("docs/reference/p2-scope.md#P2-9", "docs/reference/p2-scope.md#P2-9"),
    summary="Countersign and timestamp evidence bundles via a mock TSA/HSM interface (offline).",
    status=CapabilityStatus.IMPLEMENTED,
    planned_expected_fields=("tsa_timestamp_valid", "evidence_countersigned"),
    planned_metrics=("countersigned_evidence_rate",),
)
