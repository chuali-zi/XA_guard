"""Local file TSA anchor tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from xa_guard.audit.merkle import ChainStore, canonical_json
from xa_guard.audit.tsa import create_file_anchor, verify_file_anchor


def test_create_and_verify_file_anchor(tmp_path: Path):
    audit_path = tmp_path / "audit.jsonl"
    chain = ChainStore(audit_path)
    first = chain.append({"trace_id": "t1"})
    last = chain.append({"trace_id": "t2"})

    result = create_file_anchor(audit_path, anchor_path=tmp_path / "anchor.json")

    assert result.anchor_path.exists()
    assert result.manifest["version"] == "xa-guard-file-tsa-v1"
    assert result.manifest["record_count"] == 2
    assert result.manifest["audit_byte_size"] == audit_path.stat().st_size
    assert result.manifest["anchor_sequence"] == 1
    assert result.manifest["previous_anchor_hash"] == ""
    assert result.manifest["first_record_hash"] == first["record_hash"]
    assert result.manifest["anchored_record_hash"] == last["record_hash"]
    assert result.manifest["tsa_token"].startswith("file-tsa-v1:sha256:")
    assert (tmp_path / "index.jsonl").exists()

    verified = verify_file_anchor(audit_path, result.anchor_path, verify_index=True)
    assert verified.manifest["anchor_hash"] == result.manifest["anchor_hash"]


def test_verify_file_anchor_rejects_tampered_audit(tmp_path: Path):
    audit_path = tmp_path / "audit.jsonl"
    chain = ChainStore(audit_path)
    chain.append({"trace_id": "t1"})
    chain.append({"trace_id": "t2"})
    result = create_file_anchor(audit_path, anchor_path=tmp_path / "anchor.json")

    lines = audit_path.read_text(encoding="utf-8").splitlines()
    second = json.loads(lines[1])
    second["trace_id"] = "tampered"
    lines[1] = canonical_json(second).decode("utf-8")
    audit_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="audit verification failed"):
        verify_file_anchor(audit_path, result.anchor_path)


def test_verify_file_anchor_rejects_stale_anchor(tmp_path: Path):
    audit_path = tmp_path / "audit.jsonl"
    chain = ChainStore(audit_path)
    chain.append({"trace_id": "t1"})
    result = create_file_anchor(audit_path, anchor_path=tmp_path / "anchor.json")

    chain.append({"trace_id": "t2"})

    with pytest.raises(ValueError, match="mismatch"):
        verify_file_anchor(audit_path, result.anchor_path)


def test_create_file_anchor_chains_index_entries(tmp_path: Path):
    audit_path = tmp_path / "audit.jsonl"
    chain = ChainStore(audit_path)
    chain.append({"trace_id": "t1"})
    first = create_file_anchor(audit_path, anchor_path=tmp_path / "anchor-1.json")

    chain.append({"trace_id": "t2"})
    second = create_file_anchor(audit_path, anchor_path=tmp_path / "anchor-2.json")

    assert second.manifest["anchor_sequence"] == 2
    assert second.manifest["previous_anchor_hash"] == first.manifest["anchor_hash"]
    verify_file_anchor(audit_path, second.anchor_path, verify_index=True)


def test_create_and_verify_file_anchor_with_sm2_tsa_token(tmp_path: Path):
    """Regression for BUG-R9: an anchor with an SM2 TSA token attached must
    still verify, because the ``sm2_tsa_*`` metadata is added after
    ``anchor_hash`` is computed and must be excluded from the hash payload.
    Skipped when gmssl is unavailable (non-GM environments).
    """
    pytest.importorskip("gmssl")
    from xa_guard.audit.sm_crypto import generate_sm2_keypair, write_sm2_keyfile

    audit_path = tmp_path / "audit.jsonl"
    chain = ChainStore(audit_path, algo="sm3")
    chain.append({"trace_id": "t1"})
    chain.append({"trace_id": "t2"})

    key_path = tmp_path / "tsa.key"
    priv, pub = generate_sm2_keypair()
    write_sm2_keyfile(str(key_path), priv, pub)

    token_path = tmp_path / "tsa.token.json"
    result = create_file_anchor(
        audit_path,
        anchor_path=tmp_path / "anchor.json",
        algo="sm3",
        tsa_key_path=str(key_path),
        tsa_token_path=token_path,
    )

    # The SM2 TSA token metadata is attached after anchor_hash is computed.
    assert "sm2_tsa_token_path" in result.manifest
    assert result.manifest["sm2_tsa_signature_algo"] == "SM2-with-SM3"
    assert token_path.exists()

    # The anchor must verify round-trip with the SM2 TSA token present
    # (this is what failed before BUG-R9 was fixed).
    verified = verify_file_anchor(audit_path, result.anchor_path, algo="sm3", verify_index=True)
    assert verified.manifest["anchor_hash"] == result.manifest["anchor_hash"]
