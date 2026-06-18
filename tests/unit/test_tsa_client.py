"""TSA client (SM2-signed timestamp token) unit tests.

Locks the L3 'TSA' evidence shape required by PRD §2.2 / §4.5:
- create_timestamp_token binds an audit anchor hash to a signed UTC time via
  real SM2 (GB/T 32918), producing a 128-hex signature (not HMAC).
- verify_timestamp_token accepts the real token, rejects tampered data / forged
  signatures / mismatched anchor hash.
- token persists to JSON and reloads verifiably.
- external TSA query path is honestly recorded (no fabricated external success).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from xa_guard.audit.sm_crypto import generate_sm2_keypair, write_sm2_keyfile
from xa_guard.audit.tsa_client import (
    TimestampToken,
    create_timestamp_token,
    create_timestamp_token_with_external,
    verify_timestamp_token,
    write_token,
)


def _tsa_key(tmp_path: Path) -> str:
    pytest.importorskip("gmssl")
    priv, pub = generate_sm2_keypair()
    kp = tmp_path / "tsa.key"
    write_sm2_keyfile(kp, priv, pub)
    return str(kp)


def test_timestamp_token_signs_with_real_sm2(tmp_path: Path) -> None:
    kp = _tsa_key(tmp_path)
    anchor = "a" * 64
    tok = create_timestamp_token(anchor, tsa_key_path=kp, prefer_gm=True)
    assert tok.token["version"] == "xa-guard-tsa-token-v1"
    assert tok.token["signature_algo"] == "SM2-with-SM3"
    assert tok.token["anchor_hash"] == anchor
    sig = tok.token["signature"]
    assert len(sig) == 128  # real SM2 r||s, not HMAC 64
    assert all(c in "0123456789abcdef" for c in sig)


def test_timestamp_token_verify_roundtrip(tmp_path: Path) -> None:
    kp = _tsa_key(tmp_path)
    anchor = "b" * 64
    tok = create_timestamp_token(anchor, tsa_key_path=kp, prefer_gm=True)
    assert verify_timestamp_token(tok.token, tsa_pub_path=kp, anchor_hash=anchor, prefer_gm=True) is True


def test_timestamp_token_rejects_wrong_anchor(tmp_path: Path) -> None:
    kp = _tsa_key(tmp_path)
    tok = create_timestamp_token("c" * 64, tsa_key_path=kp, prefer_gm=True)
    assert verify_timestamp_token(tok.token, tsa_pub_path=kp, anchor_hash="d" * 64, prefer_gm=True) is False


def test_timestamp_token_rejects_forged_signature(tmp_path: Path) -> None:
    kp = _tsa_key(tmp_path)
    anchor = "e" * 64
    tok = create_timestamp_token(anchor, tsa_key_path=kp, prefer_gm=True)
    forged = dict(tok.token)
    forged["signature"] = "f" * 128
    assert verify_timestamp_token(forged, tsa_pub_path=kp, anchor_hash=anchor, prefer_gm=True) is False


def test_timestamp_token_rejects_tampered_time(tmp_path: Path) -> None:
    kp = _tsa_key(tmp_path)
    anchor = "1" * 64
    tok = create_timestamp_token(anchor, tsa_key_path=kp, prefer_gm=True)
    tampered = dict(tok.token)
    tampered["utc_time"] = "2099-01-01T00:00:00Z"
    assert verify_timestamp_token(tampered, tsa_pub_path=kp, anchor_hash=anchor, prefer_gm=True) is False


def test_timestamp_token_persists_and_reloads(tmp_path: Path) -> None:
    kp = _tsa_key(tmp_path)
    anchor = "2" * 64
    tok = create_timestamp_token(anchor, tsa_key_path=kp, prefer_gm=True)
    tp = tmp_path / "tsa.token.json"
    write_token(tok, tp)
    assert verify_timestamp_token(tp, tsa_pub_path=kp, anchor_hash=anchor, prefer_gm=True) is True


def test_external_tsa_query_recorded_honestly(tmp_path: Path) -> None:
    """External TSA URL that cannot be reached is recorded as fail, not fabricated."""
    kp = _tsa_key(tmp_path)
    anchor = "3" * 64
    tok = create_timestamp_token_with_external(
        anchor,
        tsa_key_path=kp,
        external_tsa_url="http://127.0.0.1:1/no-such-tsa",  # unreachable
        external_timeout=2,
        prefer_gm=True,
    )
    ext = tok.token.get("external_tsa")
    assert ext is not None
    assert ext["status"] == "fail"
    assert ext["error"]  # honest failure record
    # Local SM2 token still verifies even if external query failed
    assert verify_timestamp_token(tok.token, tsa_pub_path=kp, anchor_hash=anchor, prefer_gm=True) is True
