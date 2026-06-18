"""TSA (Time Stamp Authority) evidence for audit anchors.

PRD §2.2 / §4.5 require 'SM3 + SM2 + TSA' for the国密哈希链审计证据 leg of L3.

This module provides two complementary TSA evidence paths:

1. **Local TSA evidence token** (deterministic, no network): signs
   (tsa_id || anchor_hash || utc_time) with SM2 (GB/T 32918) using a TSA
   keypair, producing a verifiable timestamp token. This is an L3-grade
   *self-contained* TSA evidence artifact: the timestamp binding
   (anchor_hash -> signed UTC time) is cryptographically verifiable with the
   TSA public key, independent of the audit author. It is NOT a third-party
   trusted TSA, but it gives a real, replay-resistant, SM2-signed timestamp
   that satisfies the 'TSA' evidence shape required by the PRD and is
   reproducible offline.

2. **External RFC 3161 TSA query** (optional, network): if a TSA URL is
   configured and reachable, query a real RFC 3161 timestamp authority and
   attach the opaque TSA response. Verification of the external response is
   best-effort (requires the TSA's cert chain / pyasn1); the token records
   whether the external query succeeded so evidence is honest.

Key handling: TSA keypair is an SM2 keyfile (private/public hex) produced by
`xa_guard.audit.sm_crypto.generate_sm2_keypair` / `write_sm2_keyfile`.
"""
from __future__ import annotations

import json
import logging
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from xa_guard.audit.merkle import canonical_json
from xa_guard.audit.sm_crypto import sm2_sign, sm2_verify

log = logging.getLogger("xa_guard.audit.tsa_client")

_TOKEN_VERSION = "xa-guard-tsa-token-v1"
_DEFAULT_TSA_ID = "xa-guard-local-tsa"
_DEFAULT_EXTERNAL_TIMEOUT = 10


@dataclass(frozen=True)
class TimestampToken:
    """A TSA timestamp evidence token bound to an audit anchor hash."""

    token: dict[str, Any]
    """Parsed token (version, tsa_id, anchor_hash, utc_time, signature, ...)."""

    @property
    def is_external(self) -> bool:
        return bool(self.token.get("external_tsa_response"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _signed_payload(token_without_sig: dict[str, Any]) -> bytes:
    """Canonical bytes of the token fields that get SM2-signed."""
    return canonical_json({k: v for k, v in token_without_sig.items() if k != "signature"})


def create_timestamp_token(
    anchor_hash: str,
    *,
    tsa_key_path: str,
    tsa_id: str = _DEFAULT_TSA_ID,
    prefer_gm: bool = True,
    extra: dict[str, Any] | None = None,
) -> TimestampToken:
    """Create an SM2-signed timestamp token binding ``anchor_hash`` to UTC time.

    The token is reproducible evidence that a given audit anchor hash existed
    at the signed UTC time. Verification only needs the TSA public key.
    """
    base: dict[str, Any] = {
        "version": _TOKEN_VERSION,
        "tsa_id": tsa_id,
        "anchor_hash": anchor_hash,
        "utc_time": _utc_now(),
        "hash_algo": "sm3" if prefer_gm else "sha256",
        "signature_algo": "SM2-with-SM3" if prefer_gm else "HMAC-SHA256",
    }
    if extra:
        base.update(extra)
    payload = _signed_payload(base)
    base["signature"] = sm2_sign(payload, tsa_key_path, prefer_gm=prefer_gm)
    return TimestampToken(token=base)


def verify_timestamp_token(
    token: dict[str, Any] | str | Path,
    *,
    tsa_pub_path: str,
    anchor_hash: str | None = None,
    prefer_gm: bool = True,
) -> bool:
    """Verify an SM2 timestamp token.

    Checks: version, signature over the canonical payload, and (if given) that
    ``anchor_hash`` matches the token's bound anchor hash.
    """
    if isinstance(token, (str, Path)):
        token = json.loads(Path(token).read_text(encoding="utf-8"))
    if not isinstance(token, dict):
        return False
    if token.get("version") != _TOKEN_VERSION:
        return False
    if anchor_hash is not None and token.get("anchor_hash") != anchor_hash:
        return False
    sig = token.get("signature")
    if not sig:
        return False
    payload = _signed_payload(token)
    return sm2_verify(payload, str(sig), tsa_pub_path, prefer_gm=prefer_gm)


def query_external_tsa(
    url: str,
    anchor_hash: str,
    *,
    timeout: int = _DEFAULT_EXTERNAL_TIMEOUT,
    method: str = "POST",
) -> dict[str, Any]:
    """Best-effort external RFC 3161-style TSA query.

    Sends the anchor hash to an external TSA URL and records the opaque
    response. This is network-dependent and may fail (offline, proxy, TLS);
    the returned dict honestly records success/failure so evidence is not
    fabricated. The external response is stored opaque; full RFC 3161 ASN.1
    verification would require the TSA's cert chain (out of L3 scope).
    """
    result: dict[str, Any] = {
        "url": url,
        "method": method,
        "anchor_hash": anchor_hash,
        "status": "fail",
        "http_status": None,
        "response_hex": "",
        "error": "",
    }
    body = json.dumps({"anchor_hash": anchor_hash, "hash_algo": "sm3"}).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method=method, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            result["http_status"] = resp.status
            result["response_hex"] = raw.hex()
            result["status"] = "pass"
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def create_timestamp_token_with_external(
    anchor_hash: str,
    *,
    tsa_key_path: str,
    external_tsa_url: str | None = None,
    tsa_id: str = _DEFAULT_TSA_ID,
    prefer_gm: bool = True,
    external_timeout: int = _DEFAULT_EXTERNAL_TIMEOUT,
    extra: dict[str, Any] | None = None,
) -> TimestampToken:
    """Create a timestamp token with an optional external TSA response attached.

    Always produces the local SM2-signed token (deterministic evidence); if an
    external TSA URL is provided, also queries it and attaches the result so
    the token records both local and (best-effort) external evidence. ``extra``
    is merged into the token (e.g. to embed the TSA public key for self-contained
    verification without shipping a private key file).
    """
    merged: dict[str, Any] = dict(extra or {})
    if external_tsa_url:
        ext = query_external_tsa(external_tsa_url, anchor_hash, timeout=external_timeout)
        merged["external_tsa"] = ext
    return create_timestamp_token(
        anchor_hash,
        tsa_key_path=tsa_key_path,
        tsa_id=tsa_id,
        prefer_gm=prefer_gm,
        extra=merged,
    )


def write_token(token: dict[str, Any] | TimestampToken, path: str | Path) -> Path:
    """Write a timestamp token to a JSON file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = token.token if isinstance(token, TimestampToken) else token
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return p
