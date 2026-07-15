"""Envelope encryption and signed, short-lived compensation authorization."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.keywrap import InvalidUnwrap, aes_key_unwrap, aes_key_wrap


class CryptoError(RuntimeError):
    pass


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _decode_key(value: str) -> bytes:
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        try:
            raw = bytes.fromhex(value)
        except ValueError as exc:
            raise CryptoError("key must be base64 or hex") from exc
    if len(raw) != 32:
        raise CryptoError("key must contain exactly 32 bytes")
    return raw


@dataclass(frozen=True)
class EncryptedEnvelope:
    key_id: str
    wrapped_dek: bytes
    nonce: bytes
    ciphertext: bytes


class Keyring:
    """Versioned KEKs; each record receives an independent random DEK."""

    def __init__(self, keys: dict[str, bytes], active_key_id: str) -> None:
        if active_key_id not in keys:
            raise CryptoError("active KEK is not present in keyring")
        if not keys or any(len(key) != 32 for key in keys.values()):
            raise CryptoError("every KEK must contain exactly 32 bytes")
        self.keys = dict(keys)
        self.active_key_id = active_key_id

    @classmethod
    def from_json(cls, raw: str) -> "Keyring":
        try:
            value = json.loads(raw)
            active = str(value["active"])
            keys = {str(k): _decode_key(str(v)) for k, v in dict(value["keys"]).items()}
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise CryptoError("invalid keyring JSON") from exc
        return cls(keys, active)

    def encrypt(self, plaintext: bytes, aad: bytes) -> EncryptedEnvelope:
        dek = os.urandom(32)
        nonce = os.urandom(12)
        key_id, wrapped_dek = self.wrap_key(dek)
        return EncryptedEnvelope(
            key_id=key_id,
            wrapped_dek=wrapped_dek,
            nonce=nonce,
            ciphertext=AESGCM(dek).encrypt(nonce, plaintext, aad),
        )

    def decrypt(self, envelope: EncryptedEnvelope, aad: bytes) -> bytes:
        try:
            dek = self.unwrap_key(envelope.key_id, envelope.wrapped_dek)
            return AESGCM(dek).decrypt(envelope.nonce, envelope.ciphertext, aad)
        except (InvalidTag, InvalidUnwrap, ValueError) as exc:
            raise CryptoError("recovery material authentication failed") from exc

    def rewrap(self, envelope: EncryptedEnvelope) -> EncryptedEnvelope:
        key_id, wrapped_dek = self.rewrap_key(envelope.key_id, envelope.wrapped_dek)
        return EncryptedEnvelope(
            key_id=key_id,
            wrapped_dek=wrapped_dek,
            nonce=envelope.nonce,
            ciphertext=envelope.ciphertext,
        )

    def wrap_key(self, plaintext_key: bytes) -> tuple[str, bytes]:
        if len(plaintext_key) != 32:
            raise CryptoError("plaintext data key must contain exactly 32 bytes")
        return (
            self.active_key_id,
            aes_key_wrap(self.keys[self.active_key_id], plaintext_key),
        )

    def unwrap_key(self, key_id: str, wrapped_key: bytes) -> bytes:
        kek = self.keys.get(key_id)
        if kek is None:
            raise CryptoError("requested KEK is unavailable")
        try:
            plaintext_key = aes_key_unwrap(kek, wrapped_key)
        except (InvalidUnwrap, ValueError) as exc:
            raise CryptoError("wrapped data key authentication failed") from exc
        if len(plaintext_key) != 32:
            raise CryptoError("unwrapped data key has invalid length")
        return plaintext_key

    def rewrap_key(self, key_id: str, wrapped_key: bytes) -> tuple[str, bytes]:
        plaintext_key = self.unwrap_key(key_id, wrapped_key)
        return self.wrap_key(plaintext_key)


class InternalAuthorization:
    """HMAC authorization bound to one effect/request/approver/argument hash."""

    def __init__(self, key: bytes, issuer: str = "xa-guard-control") -> None:
        if len(key) < 32:
            raise CryptoError("internal authorization key must be at least 32 bytes")
        self.key = key
        self.issuer = issuer

    def issue(self, claims: dict[str, Any], ttl_seconds: int = 900) -> str:
        reserved = {"iss", "iat", "exp"}.intersection(claims)
        if reserved:
            raise CryptoError(f"reserved internal authorization claims: {', '.join(sorted(reserved))}")
        if ttl_seconds <= 0 or ttl_seconds > 3600:
            raise CryptoError("internal authorization TTL must be between 1 and 3600 seconds")
        now = int(time.time())
        payload = {**claims, "iss": self.issuer, "iat": now, "exp": now + ttl_seconds}
        body = base64.urlsafe_b64encode(canonical_json(payload)).rstrip(b"=")
        sig = hmac.new(self.key, body, hashlib.sha256).digest()
        return body.decode() + "." + base64.urlsafe_b64encode(sig).rstrip(b"=").decode()

    def verify(self, token: str, expected: dict[str, str] | None = None) -> dict[str, Any]:
        payload = self._verified_payload(token, allow_expired=False)
        self._verify_bindings(payload, expected)
        return payload

    def verify_for_admin_retry(
        self, token: str, expected: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """Authenticate a stored approval even after its execution TTL elapsed.

        This method deliberately does not make the old token executable again.  It
        only recovers authenticated, effect-bound claims so a currently
        authenticated ``undo.admin`` can issue a new short-lived authorization.
        Signature, issuer, issuance time, original TTL, and caller-supplied
        bindings are still checked.
        """

        payload = self._verified_payload(token, allow_expired=True)
        self._verify_bindings(payload, expected)
        return payload

    def _verified_payload(self, token: str, *, allow_expired: bool) -> dict[str, Any]:
        try:
            body_text, sig_text = token.split(".", 1)
            body = body_text.encode()
            sig = base64.urlsafe_b64decode(sig_text + "=" * (-len(sig_text) % 4))
            payload = json.loads(base64.urlsafe_b64decode(body_text + "=" * (-len(body_text) % 4)))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise CryptoError("invalid internal authorization") from exc
        if not isinstance(payload, dict):
            raise CryptoError("invalid internal authorization")
        if not hmac.compare_digest(sig, hmac.new(self.key, body, hashlib.sha256).digest()):
            raise CryptoError("invalid internal authorization signature")
        now = int(time.time())
        try:
            issued_at = int(payload.get("iat", 0))
            expires_at = int(payload.get("exp", 0))
        except (TypeError, ValueError) as exc:
            raise CryptoError("invalid internal authorization timestamps") from exc
        if (
            payload.get("iss") != self.issuer
            or issued_at <= 0
            or expires_at <= issued_at
            or issued_at > now + 30
            or expires_at - issued_at > 3600
            or (not allow_expired and expires_at <= now)
        ):
            raise CryptoError("internal authorization is expired or has wrong issuer")
        return payload

    @staticmethod
    def _verify_bindings(payload: dict[str, Any], expected: dict[str, str] | None) -> None:
        for key, value in (expected or {}).items():
            if str(payload.get(key) or "") != value:
                raise CryptoError(f"internal authorization is not bound to {key}")
