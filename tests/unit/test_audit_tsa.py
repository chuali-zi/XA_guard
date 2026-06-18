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
