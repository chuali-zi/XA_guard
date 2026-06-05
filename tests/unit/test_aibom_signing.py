"""Unit tests for xa_guard.aibom.signing — AIBOM JSF-style sign + verify.

Coverage
--------
(a) Ed25519 sign+verify round-trip with a real BOM produced by export_cyclonedx.
(b) Tampered BOM → verified=False.
(c) Unknown keyId / empty trust store → verified=False with error.
(d) HMAC algorithm round-trip.
(e) canonicalize is stable regardless of input key order; excludes signature field.
(f) cryptography unavailable (monkeypatched) → signing falls back to HMAC without error.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from xa_guard.aibom.signing import (
    canonicalize,
    generate_ed25519_keypair,
    sign_bom,
    verify_bom,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _minimal_plugin(tmp_path: Path) -> Path:
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    (plugin / "requirements.txt").write_text("requests==2.31.0\n", encoding="utf-8")
    (plugin / "main.py").write_text(
        "import requests\nrequests.get('https://example.com')\n",
        encoding="utf-8",
    )
    return plugin


def _real_bom(tmp_path: Path) -> dict[str, Any]:
    from xa_guard.aibom.exporter import export_cyclonedx
    from xa_guard.aibom.scanner import scan

    plugin = _minimal_plugin(tmp_path)
    return export_cyclonedx(scan(plugin))


def _make_hmac_trust_store(tmp_path: Path, key_id: str) -> tuple[Path, Path]:
    """Return (store_dir, key_file) where key_file is <key_id>.pub inside store_dir."""
    store = tmp_path / "store"
    store.mkdir(exist_ok=True)
    key_file = store / f"{key_id}.pub"
    key_file.write_bytes(b"xa-guard-test-hmac-key-for-unit-tests-only")
    return store, key_file


# ---------------------------------------------------------------------------
# (e) canonicalize
# ---------------------------------------------------------------------------

class TestCanonicalize:
    def test_deterministic_regardless_of_key_order(self) -> None:
        bom_a = {"bomFormat": "CycloneDX", "specVersion": "1.5", "version": 1}
        bom_b = {"version": 1, "specVersion": "1.5", "bomFormat": "CycloneDX"}
        assert canonicalize(bom_a) == canonicalize(bom_b)

    def test_excludes_signature_field(self) -> None:
        bom = {"bomFormat": "CycloneDX", "version": 1}
        signed = dict(bom)
        signed["signature"] = {"algorithm": "Ed25519", "keyId": "k1", "value": "deadbeef"}
        assert canonicalize(bom) == canonicalize(signed)

    def test_returns_utf8_bytes(self) -> None:
        bom = {"name": "组件"}
        result = canonicalize(bom)
        assert isinstance(result, bytes)
        result.decode("utf-8")  # must not raise

    def test_nested_structures_are_stable(self) -> None:
        bom = {
            "z_key": [3, 2, 1],
            "a_key": {"nested_b": 2, "nested_a": 1},
        }
        assert canonicalize(bom) == canonicalize(bom)


# ---------------------------------------------------------------------------
# (a) Ed25519 round-trip
# ---------------------------------------------------------------------------

class TestEd25519RoundTrip:
    def test_sign_and_verify_real_bom(self, tmp_path: pytest.TempPathFactory) -> None:
        key_id = "test-key-1"
        priv_path, pub_path = generate_ed25519_keypair(str(tmp_path / "keys"), key_id)

        bom = _real_bom(tmp_path)
        signed = sign_bom(bom, key_path=priv_path, key_id=key_id, algorithm="ed25519")

        assert "signature" not in bom  # original untouched
        assert signed["signature"]["algorithm"] == "Ed25519"
        assert signed["signature"]["keyId"] == key_id
        assert len(signed["signature"]["value"]) == 128  # 64 bytes hex

        store = tmp_path / "keys"
        result = verify_bom(signed, trust_store=str(store))
        assert result.verified is True
        assert result.algorithm == "Ed25519"
        assert result.key_id == key_id
        assert result.errors == []

    def test_keypair_files_created(self, tmp_path: pytest.TempPathFactory) -> None:
        key_id = "ops-key"
        priv, pub = generate_ed25519_keypair(str(tmp_path), key_id)
        assert Path(priv).exists()
        assert Path(pub).exists()
        assert Path(priv).suffix == ".priv"
        assert Path(pub).suffix == ".pub"

    def test_public_key_embedded_in_signature_block(self, tmp_path: pytest.TempPathFactory) -> None:
        key_id = "embed-test"
        priv_path, _ = generate_ed25519_keypair(str(tmp_path / "keys"), key_id)
        bom = {"bomFormat": "CycloneDX", "version": 1}
        signed = sign_bom(bom, key_path=priv_path, key_id=key_id, algorithm="ed25519")
        assert "publicKey" in signed["signature"]
        assert len(signed["signature"]["publicKey"]) == 64  # 32 bytes hex


# ---------------------------------------------------------------------------
# (b) Tampered BOM
# ---------------------------------------------------------------------------

class TestTampering:
    def test_tampered_bom_field_fails_verification(self, tmp_path: pytest.TempPathFactory) -> None:
        key_id = "tamper-key"
        priv_path, _ = generate_ed25519_keypair(str(tmp_path / "keys"), key_id)
        bom = _real_bom(tmp_path)
        signed = sign_bom(bom, key_path=priv_path, key_id=key_id, algorithm="ed25519")

        tampered = dict(signed)
        tampered["version"] = 999  # mutate a field

        result = verify_bom(tampered, trust_store=str(tmp_path / "keys"))
        assert result.verified is False
        assert result.errors  # must contain a descriptive error

    def test_tampered_signature_value_fails_verification(self, tmp_path: pytest.TempPathFactory) -> None:
        key_id = "tamper-sig-key"
        priv_path, _ = generate_ed25519_keypair(str(tmp_path / "keys"), key_id)
        bom = {"bomFormat": "CycloneDX", "version": 1}
        signed = sign_bom(bom, key_path=priv_path, key_id=key_id, algorithm="ed25519")

        corrupted = dict(signed)
        corrupted["signature"] = dict(signed["signature"])
        corrupted["signature"]["value"] = "a" * 128  # forged sig

        result = verify_bom(corrupted, trust_store=str(tmp_path / "keys"))
        assert result.verified is False


# ---------------------------------------------------------------------------
# (c) Unknown keyId / empty trust store
# ---------------------------------------------------------------------------

class TestUnknownKeyId:
    def test_empty_trust_store_returns_false_with_error(self, tmp_path: pytest.TempPathFactory) -> None:
        key_id = "ghost-key"
        priv_path, _ = generate_ed25519_keypair(str(tmp_path / "signing_keys"), key_id)
        bom = {"bomFormat": "CycloneDX", "version": 1}
        signed = sign_bom(bom, key_path=priv_path, key_id=key_id, algorithm="ed25519")

        empty_store = tmp_path / "empty_store"
        empty_store.mkdir()

        result = verify_bom(signed, trust_store=str(empty_store))
        assert result.verified is False
        assert result.errors
        assert any("not found" in e or "trust store" in e for e in result.errors)

    def test_wrong_key_id_in_signed_bom_fails(self, tmp_path: pytest.TempPathFactory) -> None:
        # Store has key "actual-key", but BOM was signed with "other-key"
        key_id = "other-key"
        priv_path, _ = generate_ed25519_keypair(str(tmp_path / "keys"), key_id)
        bom = {"bomFormat": "CycloneDX", "version": 1}
        signed = sign_bom(bom, key_path=priv_path, key_id=key_id, algorithm="ed25519")

        # Store only has a different key
        store = tmp_path / "store"
        store.mkdir()
        generate_ed25519_keypair(str(store), "actual-key")

        result = verify_bom(signed, trust_store=str(store))
        assert result.verified is False

    def test_no_signature_field_in_bom_returns_false(self, tmp_path: pytest.TempPathFactory) -> None:
        bom = {"bomFormat": "CycloneDX", "version": 1}
        store = tmp_path / "store"
        store.mkdir()
        result = verify_bom(bom, trust_store=str(store))
        assert result.verified is False
        assert result.errors


# ---------------------------------------------------------------------------
# (d) HMAC round-trip
# ---------------------------------------------------------------------------

class TestHmacRoundTrip:
    def test_hmac_sign_and_verify(self, tmp_path: pytest.TempPathFactory) -> None:
        store, key_file = _make_hmac_trust_store(tmp_path, "hmac-key-1")
        bom = {"bomFormat": "CycloneDX", "specVersion": "1.5", "version": 1}

        signed = sign_bom(bom, key_path=str(key_file), key_id="hmac-key-1", algorithm="hmac")

        assert signed["signature"]["algorithm"] == "HMAC-SHA256"
        result = verify_bom(signed, trust_store=str(store))
        assert result.verified is True
        assert result.algorithm == "HMAC-SHA256"
        assert result.key_id == "hmac-key-1"

    def test_hmac_tamper_fails(self, tmp_path: pytest.TempPathFactory) -> None:
        store, key_file = _make_hmac_trust_store(tmp_path, "hmac-key-2")
        bom = {"bomFormat": "CycloneDX", "version": 1}
        signed = sign_bom(bom, key_path=str(key_file), key_id="hmac-key-2", algorithm="hmac")

        tampered = dict(signed)
        tampered["extra_field"] = "injected"

        result = verify_bom(tampered, trust_store=str(store))
        assert result.verified is False

    def test_hmac_wrong_key_fails(self, tmp_path: pytest.TempPathFactory) -> None:
        _, key_file = _make_hmac_trust_store(tmp_path, "hmac-key-3")
        bom = {"bomFormat": "CycloneDX", "version": 1}
        signed = sign_bom(bom, key_path=str(key_file), key_id="hmac-key-3", algorithm="hmac")

        # Store now has a different key for the same keyId
        store2 = tmp_path / "store2"
        store2.mkdir()
        (store2 / "hmac-key-3.pub").write_bytes(b"completely-different-key-bytes")

        result = verify_bom(signed, trust_store=str(store2))
        assert result.verified is False


# ---------------------------------------------------------------------------
# (f) Fallback when cryptography is unavailable
# ---------------------------------------------------------------------------

class TestCryptographyFallback:
    def test_sign_falls_back_to_hmac_when_cryptography_unavailable(
        self,
        tmp_path: pytest.TempPathFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import xa_guard.aibom.signing as signing_mod

        # Patch _ed25519_available to return False (simulates missing cryptography)
        monkeypatch.setattr(signing_mod, "_ed25519_available", lambda: False)

        key_id = "fallback-key"
        key_file = tmp_path / f"{key_id}.key"
        key_file.write_bytes(b"fallback-test-hmac-secret-key-32b!")

        bom = {"bomFormat": "CycloneDX", "version": 1}
        # Default algorithm "ed25519" should auto-downgrade to "hmac"
        signed = sign_bom(bom, key_path=str(key_file), key_id=key_id, algorithm="ed25519")

        assert signed["signature"]["algorithm"] == "HMAC-SHA256"
        assert signed["signature"]["keyId"] == key_id

    def test_fallback_hmac_verifies_correctly(
        self,
        tmp_path: pytest.TempPathFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import xa_guard.aibom.signing as signing_mod

        monkeypatch.setattr(signing_mod, "_ed25519_available", lambda: False)

        key_id = "fallback-verify-key"
        key_file = tmp_path / f"{key_id}.pub"
        key_file.write_bytes(b"shared-symmetric-key-for-fallback-test!")

        store = tmp_path
        bom = {"bomFormat": "CycloneDX", "version": 1}
        signed = sign_bom(bom, key_path=str(key_file), key_id=key_id, algorithm="ed25519")

        # Verify without monkeypatch interference (HMAC path doesn't need cryptography)
        result = verify_bom(signed, trust_store=str(store))
        assert result.verified is True


# ---------------------------------------------------------------------------
# Additional edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_sign_does_not_mutate_original_bom(self, tmp_path: pytest.TempPathFactory) -> None:
        key_id = "no-mutate"
        priv_path, _ = generate_ed25519_keypair(str(tmp_path / "keys"), key_id)
        bom = {"bomFormat": "CycloneDX", "version": 1}
        original_keys = set(bom.keys())

        sign_bom(bom, key_path=priv_path, key_id=key_id, algorithm="ed25519")

        assert set(bom.keys()) == original_keys

    def test_unsupported_algorithm_raises(self, tmp_path: pytest.TempPathFactory) -> None:
        key_id = "x"
        priv_path, _ = generate_ed25519_keypair(str(tmp_path), key_id)
        bom = {"bomFormat": "CycloneDX"}
        with pytest.raises(ValueError, match="Unsupported algorithm"):
            sign_bom(bom, key_path=priv_path, key_id=key_id, algorithm="rsa4096")

    def test_verify_incomplete_signature_block(self, tmp_path: pytest.TempPathFactory) -> None:
        bom = {"bomFormat": "CycloneDX", "signature": {"algorithm": "Ed25519"}}
        store = tmp_path / "store"
        store.mkdir()
        result = verify_bom(bom, trust_store=str(store))
        assert result.verified is False
        assert result.errors

    def test_sign_bom_existing_signature_is_replaced(self, tmp_path: pytest.TempPathFactory) -> None:
        key_id = "replace-sig"
        priv_path, _ = generate_ed25519_keypair(str(tmp_path / "keys"), key_id)
        bom = {"bomFormat": "CycloneDX", "version": 1, "signature": {"algorithm": "old", "value": "stale"}}
        signed = sign_bom(bom, key_path=priv_path, key_id=key_id, algorithm="ed25519")
        assert signed["signature"]["algorithm"] == "Ed25519"
