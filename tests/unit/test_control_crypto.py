from __future__ import annotations

import json

import pytest

from xa_guard.control.crypto import CryptoError, InternalAuthorization, Keyring


def test_envelope_uses_random_deks_and_supports_rewrap() -> None:
    aad = b"tenant/effect/tool"
    plaintext = b'{"ticket_id":"TKT-1"}'
    old = b"a" * 32
    new = b"b" * 32
    first_ring = Keyring({"v1": old}, "v1")
    one = first_ring.encrypt(plaintext, aad)
    two = first_ring.encrypt(plaintext, aad)
    assert one.ciphertext != two.ciphertext
    assert one.wrapped_dek != two.wrapped_dek

    rotated = Keyring({"v1": old, "v2": new}, "v2")
    rewrapped = rotated.rewrap(one)
    assert rewrapped.key_id == "v2"
    assert rewrapped.ciphertext == one.ciphertext
    assert rotated.decrypt(rewrapped, aad) == plaintext


def test_wrong_kek_and_wrong_aad_fail_closed() -> None:
    envelope = Keyring({"v1": b"a" * 32}, "v1").encrypt(b"secret", b"correct")
    with pytest.raises(CryptoError):
        Keyring({"v1": b"b" * 32}, "v1").decrypt(envelope, b"correct")
    with pytest.raises(CryptoError):
        Keyring({"v1": b"a" * 32}, "v1").decrypt(envelope, b"wrong")


def test_internal_authorization_is_bound_and_reserved_claims_cannot_override() -> None:
    signer = InternalAuthorization(b"k" * 32)
    token = signer.issue({"effect_id": "eff-1", "request_id": "undo-1"}, ttl_seconds=60)
    claims = signer.verify(token, {"effect_id": "eff-1", "request_id": "undo-1"})
    assert claims["effect_id"] == "eff-1"
    with pytest.raises(CryptoError):
        signer.verify(token, {"effect_id": "eff-other"})
    with pytest.raises(CryptoError):
        signer.issue({"exp": 9999999999})
    with pytest.raises(CryptoError):
        signer.issue({"effect_id": "eff-1"}, ttl_seconds=3601)


def test_keyring_json_requires_active_32_byte_key() -> None:
    with pytest.raises(CryptoError):
        Keyring.from_json(json.dumps({"active": "missing", "keys": {}}))

