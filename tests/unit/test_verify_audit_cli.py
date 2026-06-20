from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts import verify_audit
from xa_guard.audit.merkle import canonical_json, compute_record_hash
from xa_guard.audit.sm_crypto import hmac_demo_key_id, sm2_sign


def _run_main(monkeypatch, audit_path: Path, *extra: str) -> int:
    monkeypatch.setattr(
        sys,
        "argv",
        ["verify_audit.py", "--path", str(audit_path), *extra],
    )
    return verify_audit.main()


def _write_record(path: Path, record: dict[str, object]) -> None:
    record["record_hash"] = compute_record_hash(record)
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")


def _minimal_audit_record() -> dict[str, object]:
    return {
        "trace_id": "trace-1",
        "span_id": "span-1",
        "timestamp": "2026-06-18T00:00:00Z",
        "gen_ai.tool.name": "read_file",
        "gen_ai.tool.parameters": {},
        "gen_ai.tool.result.hash": "result-hash",
        "gen_ai.user.role": "user",
        "gen_ai.data.sensitivity_level": "public",
        "gen_ai.policy.hit_id": "policy-1",
        "gen_ai.evidence.hash_prev": "",
    }


def test_main_returns_nonzero_for_invalid_json(tmp_path: Path, monkeypatch) -> None:
    audit_path = tmp_path / "audit.jsonl"
    audit_path.write_text("{not-json}\n", encoding="utf-8")

    assert _run_main(monkeypatch, audit_path) != 0


def test_main_returns_nonzero_for_missing_required_field(tmp_path: Path, monkeypatch) -> None:
    audit_path = tmp_path / "audit.jsonl"
    record = _minimal_audit_record()
    del record["span_id"]
    _write_record(audit_path, record)

    assert _run_main(monkeypatch, audit_path) != 0


def test_main_returns_zero_for_minimal_valid_audit(tmp_path: Path, monkeypatch) -> None:
    audit_path = tmp_path / "audit.jsonl"
    _write_record(audit_path, _minimal_audit_record())

    assert _run_main(monkeypatch, audit_path) == 0


def test_main_can_require_and_detect_tampered_demo_signature(tmp_path: Path, monkeypatch) -> None:
    audit_path = tmp_path / "audit.jsonl"
    record = _minimal_audit_record()
    record["signature_algorithm"] = "HMAC-SHA256-DEMO"
    record["signature_key_id"] = hmac_demo_key_id("")
    record["record_hash"] = compute_record_hash(record)
    record["signature"] = sm2_sign(canonical_json(record), "", prefer_gm=False)
    audit_path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    assert _run_main(monkeypatch, audit_path, "--require-signature", "hmac-demo") == 0

    record["signature"] = "0" * 64
    audit_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    assert _run_main(monkeypatch, audit_path, "--require-signature", "hmac-demo") != 0
