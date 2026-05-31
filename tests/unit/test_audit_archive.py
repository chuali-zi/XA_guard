"""Audit log rotation/archive tests."""
from __future__ import annotations

import json
from pathlib import Path

from xa_guard.audit.archive import archive_audit_log
from xa_guard.audit.merkle import ChainStore, canonical_json


def test_archive_audit_log_preserves_corrupt_source_and_writes_manifest(tmp_path: Path):
    audit_path = tmp_path / "logs" / "audit" / "audit.jsonl"
    chain = ChainStore(audit_path)
    chain.append({"trace_id": "t1"})
    chain.append({"trace_id": "t2"})

    lines = audit_path.read_text(encoding="utf-8").splitlines()
    second = json.loads(lines[1])
    second["trace_id"] = "tampered"
    lines[1] = canonical_json(second).decode("utf-8")
    original_bytes = ("\n".join(lines) + "\n").encode("utf-8")
    audit_path.write_bytes(original_bytes)

    result = archive_audit_log(
        audit_path,
        archive_dir=tmp_path / "logs" / "audit" / "archive",
        reason="known-corrupt-sample",
    )

    assert not audit_path.exists()
    assert result.archive_path.read_bytes() == original_bytes
    assert result.manifest_path.exists()

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["source_path"] == str(audit_path)
    assert manifest["archive_path"] == str(result.archive_path)
    assert manifest["record_count"] == 2
    assert manifest["verify"]["ok"] is False
    assert manifest["verify"]["error_count"] == 1
    assert manifest["verify"]["first_error_line"] == 2
    assert manifest["reason"] == "known-corrupt-sample"
    assert manifest["archived_at"]
