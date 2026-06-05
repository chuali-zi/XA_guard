"""AIBOM JSF-style signing and verification — 赛题方向 3.

Algorithms
----------
- ``ed25519``  Real asymmetric signature via :mod:`cryptography` (primary path).
- ``sm2``      Via :mod:`xa_guard.audit.sm_crypto`; falls back to HMAC-SHA256 when
               *gmssl* is absent (documented demo fallback).
- ``hmac``     stdlib HMAC-SHA256 symmetric demo.

Trust-store convention
----------------------
A directory whose files are named ``<keyId>.pub`` (Ed25519 raw-bytes-as-hex or PEM)
and/or ``<keyId>.key`` (HMAC / SM2 symmetric demo key bytes).  Verification looks up
``<keyId>.pub`` first; falls back to ``<keyId>.key`` for symmetric algorithms.

Canonical serialisation
-----------------------
Signatures cover the BOM with the ``"signature"`` field removed, then
``json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False)``
encoded as UTF-8.  This is deterministic across Python dicts regardless of key order.
"""
from __future__ import annotations

import hashlib
import hmac as _hmac
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("xa_guard.aibom.signing")

# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------

@dataclass
class SignatureResult:
    verified: bool
    algorithm: str = ""
    key_id: str = ""
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Canonical serialisation
# ---------------------------------------------------------------------------

def canonicalize(bom: dict[str, Any]) -> bytes:
    """Return deterministic UTF-8 JSON of *bom* with any ``"signature"`` key stripped."""
    clean: dict[str, Any] = {k: v for k, v in bom.items() if k != "signature"}
    return json.dumps(clean, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


# ---------------------------------------------------------------------------
# Ed25519 helpers (lazy import)
# ---------------------------------------------------------------------------

def _ed25519_available() -> bool:
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: F401
        return True
    except Exception:
        return False


def _ed25519_sign(data: bytes, key_path: str) -> str:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    raw = Path(key_path).read_bytes()
    if raw[:1] == b"-":  # PEM
        private_key = load_pem_private_key(raw, password=None)
    else:
        private_key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(raw.decode().strip()))
    sig_bytes = private_key.sign(data)  # type: ignore[attr-defined]
    return sig_bytes.hex()


def _ed25519_pub_hex(key_path: str) -> str:
    """Return raw public key hex from a private key file (for embedding in signature block)."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        PublicFormat,
        load_pem_private_key,
    )

    raw = Path(key_path).read_bytes()
    if raw[:1] == b"-":  # PEM
        private_key = load_pem_private_key(raw, password=None)
    else:
        private_key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(raw.decode().strip()))
    pub = private_key.public_key()  # type: ignore[attr-defined]
    return pub.public_bytes(Encoding.Raw, PublicFormat.Raw).hex()


def _ed25519_verify(data: bytes, sig_hex: str, pub_path: str) -> bool:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    from cryptography.exceptions import InvalidSignature

    raw = Path(pub_path).read_bytes()
    if raw[:1] == b"-":  # PEM
        pub_key = load_pem_public_key(raw)
    else:
        pub_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(raw.decode().strip()))
    try:
        pub_key.verify(bytes.fromhex(sig_hex), data)  # type: ignore[attr-defined]
        return True
    except InvalidSignature:
        return False


# ---------------------------------------------------------------------------
# HMAC helpers
# ---------------------------------------------------------------------------

def _hmac_sign(data: bytes, key_path: str) -> str:
    key = Path(key_path).read_bytes()
    return _hmac.new(key, data, hashlib.sha256).hexdigest()


def _hmac_verify(data: bytes, sig_hex: str, key_path: str) -> bool:
    key = Path(key_path).read_bytes()
    expected = _hmac.new(key, data, hashlib.sha256).hexdigest()
    return _hmac.compare_digest(expected, sig_hex)


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def sign_bom(
    bom: dict[str, Any],
    *,
    key_path: str,
    key_id: str,
    algorithm: str = "ed25519",
) -> dict[str, Any]:
    """Return a new dict that is *bom* plus a JSF-style ``"signature"`` block.

    The input *bom* is never mutated.

    Parameters
    ----------
    bom:
        Plain CycloneDX dict (as produced by :func:`~xa_guard.aibom.exporter.export_cyclonedx`).
    key_path:
        Path to the signing key file.  For ``ed25519`` this is the private key
        (raw hex or PEM).  For ``hmac``/``sm2`` it is the symmetric key file.
    key_id:
        Logical identifier matching the trust-store filename ``<keyId>.pub`` /
        ``<keyId>.key``.
    algorithm:
        One of ``"ed25519"``, ``"sm2"``, ``"hmac"``.  Defaults to ``"ed25519"``
        when :mod:`cryptography` is available, otherwise ``"hmac"``.
    """
    alg = algorithm.lower()
    # Auto-resolve default
    if alg == "ed25519" and not _ed25519_available():
        log.warning("cryptography unavailable — falling back to hmac for signing")
        alg = "hmac"

    canonical = canonicalize(bom)

    if alg == "ed25519":
        sig_value = _ed25519_sign(canonical, key_path)
        pub_hex = _ed25519_pub_hex(key_path)
        sig_block: dict[str, str] = {
            "algorithm": "Ed25519",
            "keyId": key_id,
            "value": sig_value,
            "publicKey": pub_hex,
        }
    elif alg == "sm2":
        try:
            from xa_guard.audit.sm_crypto import sm2_sign  # lazy
        except ImportError as exc:
            raise ImportError("xa_guard.audit.sm_crypto not found") from exc
        sig_value = sm2_sign(canonical, key_path, prefer_gm=True)
        sig_block = {"algorithm": "SM2", "keyId": key_id, "value": sig_value}
    elif alg == "hmac":
        sig_value = _hmac_sign(canonical, key_path)
        sig_block = {"algorithm": "HMAC-SHA256", "keyId": key_id, "value": sig_value}
    else:
        raise ValueError(f"Unsupported algorithm: {algorithm!r}. Choose ed25519, sm2, or hmac.")

    signed_bom = dict(bom)
    signed_bom["signature"] = sig_block
    return signed_bom


def verify_bom(bom: dict[str, Any], *, trust_store: str) -> SignatureResult:
    """Verify the ``"signature"`` block inside *bom* against the trust store.

    Parameters
    ----------
    bom:
        Signed BOM dict containing a ``"signature"`` key.
    trust_store:
        Directory path.  Keys are resolved as ``<keyId>.pub`` (asymmetric) and/or
        ``<keyId>.key`` (symmetric).

    Returns
    -------
    :class:`SignatureResult` with ``verified=True`` only when all checks pass.
    Fail-closed: unknown keyId or missing trust-store entries always return
    ``verified=False`` with a descriptive error.
    """
    sig_block = bom.get("signature")
    if not sig_block:
        return SignatureResult(verified=False, errors=["No signature block found in BOM"])

    alg_raw: str = sig_block.get("algorithm", "")
    key_id: str = sig_block.get("keyId", "")
    sig_value: str = sig_block.get("value", "")

    if not alg_raw or not key_id or not sig_value:
        return SignatureResult(
            verified=False,
            algorithm=alg_raw,
            key_id=key_id,
            errors=["Signature block is missing required fields (algorithm/keyId/value)"],
        )

    store = Path(trust_store)
    canonical = canonicalize(bom)
    alg_lower = alg_raw.lower()

    if alg_lower == "ed25519":
        pub_path = store / f"{key_id}.pub"
        if not pub_path.exists():
            return SignatureResult(
                verified=False,
                algorithm=alg_raw,
                key_id=key_id,
                errors=[f"Public key not found in trust store: {pub_path}"],
            )
        try:
            ok = _ed25519_verify(canonical, sig_value, str(pub_path))
        except Exception as exc:
            return SignatureResult(
                verified=False,
                algorithm=alg_raw,
                key_id=key_id,
                errors=[f"Ed25519 verification error: {exc}"],
            )
        return SignatureResult(
            verified=ok,
            algorithm=alg_raw,
            key_id=key_id,
            errors=[] if ok else ["Signature verification failed — BOM may be tampered"],
        )

    if alg_lower in {"sm2", "hmac-sha256", "hmac"}:
        # Try .pub first (may hold symmetric demo key), then .key
        key_path = store / f"{key_id}.pub"
        if not key_path.exists():
            key_path = store / f"{key_id}.key"
        if not key_path.exists():
            return SignatureResult(
                verified=False,
                algorithm=alg_raw,
                key_id=key_id,
                errors=[f"Key not found in trust store for keyId={key_id!r}"],
            )

        if alg_lower == "sm2":
            try:
                from xa_guard.audit.sm_crypto import sm2_verify  # lazy
            except ImportError as exc:
                return SignatureResult(
                    verified=False,
                    algorithm=alg_raw,
                    key_id=key_id,
                    errors=[f"sm_crypto import failed: {exc}"],
                )
            try:
                ok = sm2_verify(canonical, sig_value, str(key_path), prefer_gm=True)
            except Exception as exc:
                return SignatureResult(
                    verified=False,
                    algorithm=alg_raw,
                    key_id=key_id,
                    errors=[f"SM2 verification error: {exc}"],
                )
        else:
            try:
                ok = _hmac_verify(canonical, sig_value, str(key_path))
            except Exception as exc:
                return SignatureResult(
                    verified=False,
                    algorithm=alg_raw,
                    key_id=key_id,
                    errors=[f"HMAC verification error: {exc}"],
                )
        return SignatureResult(
            verified=ok,
            algorithm=alg_raw,
            key_id=key_id,
            errors=[] if ok else ["Signature verification failed — BOM may be tampered"],
        )

    return SignatureResult(
        verified=False,
        algorithm=alg_raw,
        key_id=key_id,
        errors=[f"Unsupported algorithm in signature block: {alg_raw!r}"],
    )


def generate_ed25519_keypair(directory: str, key_id: str) -> tuple[str, str]:
    """Generate an Ed25519 keypair and write raw-hex key files to *directory*.

    Files written
    -------------
    ``<directory>/<key_id>.priv`` — private key as lowercase hex (32 bytes raw).
    ``<directory>/<key_id>.pub``  — public key as lowercase hex (32 bytes raw).

    Returns
    -------
    ``(priv_path, pub_path)`` as absolute path strings.

    Raises
    ------
    :class:`ImportError` if :mod:`cryptography` is not installed.
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, PrivateFormat, NoEncryption

    private_key = Ed25519PrivateKey.generate()
    priv_raw = private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    pub_raw = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)

    base = Path(directory)
    base.mkdir(parents=True, exist_ok=True)
    priv_path = base / f"{key_id}.priv"
    pub_path = base / f"{key_id}.pub"
    priv_path.write_text(priv_raw.hex(), encoding="utf-8")
    pub_path.write_text(pub_raw.hex(), encoding="utf-8")
    return str(priv_path), str(pub_path)
