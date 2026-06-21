"""Local file timestamp anchors for audit JSONL evidence.

This is a deterministic, inspectable file anchor. It is useful for L3 demo and
CI evidence snapshots, but it is not a replacement for an external TSA service.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from xa_guard.audit.archive import verify_audit_jsonl
from xa_guard.audit.merkle import canonical_json

_VERSION = "xa-guard-file-tsa-v1"
_INDEX_VERSION = "xa-guard-file-tsa-index-v1"
_TOKEN_PREFIX = "file-tsa-v1"


@dataclass(frozen=True)
class FileAnchorResult:
    """Result of creating or verifying a local audit anchor."""

    audit_path: Path
    anchor_path: Path
    manifest: dict[str, Any]


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _hash_bytes(data: bytes, algo: str) -> str:
    if algo == "sm3":
        from xa_guard.audit.sm_crypto import sm3_hash

        return sm3_hash(data, prefer_gm=True)
    if algo != "sha256":
        raise ValueError(f"unsupported audit hash algo: {algo}")
    return hashlib.sha256(data).hexdigest()


def _audit_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _default_index_path(anchor_path: Path) -> Path:
    return anchor_path.parent / "index.jsonl"


def _read_last_index_entry(index_path: Path) -> dict[str, Any] | None:
    if not index_path.exists():
        return None
    last = ""
    with index_path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if line:
                last = line
    if not last:
        return None
    entry = json.loads(last)
    if not isinstance(entry, dict):
        raise ValueError(f"last anchor index entry is not a JSON object: {index_path}")
    return entry


def _append_index_entry(index_path: Path, manifest: dict[str, Any], anchor_path: Path) -> None:
    entry = {
        "version": _INDEX_VERSION,
        "sequence": manifest["anchor_sequence"],
        "created_at": manifest["created_at"],
        "audit_path": manifest["audit_path"],
        "anchor_path": str(anchor_path),
        "anchor_hash": manifest["anchor_hash"],
        "previous_anchor_hash": manifest["previous_anchor_hash"],
        "anchored_record_hash": manifest["anchored_record_hash"],
    }
    with index_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def _read_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_no, raw_line in enumerate(handle, 1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except Exception as exc:
                raise ValueError(f"audit JSON parse failed at line {line_no}: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"audit line {line_no} is not a JSON object")
            records.append(record)
    return records


def _default_anchor_path(audit_path: Path, created_at: str) -> Path:
    safe_stamp = created_at.replace(":", "").replace("-", "")
    return audit_path.parent / "anchors" / f"{audit_path.stem}-{safe_stamp}.anchor.json"


def _payload_for_hash(manifest: dict[str, Any]) -> dict[str, Any]:
    # ``anchor_hash`` and ``tsa_token`` are derived from this payload, so they
    # must not participate in their own hash. The ``sm2_tsa_*`` fields are the
    # SM2 timestamp-token metadata attached AFTER ``anchor_hash`` is computed
    # (the TSA token signs ``anchor_hash``, not the manifest body), so they are
    # also excluded to keep create-time and verify-time payloads identical.
    # Otherwise verify_file_anchor would recompute a different hash whenever an
    # SM2 TSA token was attached (BUG-R9).
    _EXCLUDED = {
        "anchor_hash",
        "tsa_token",
        "sm2_tsa_token_path",
        "sm2_tsa_signature_algo",
        "sm2_tsa_utc_time",
        "sm2_tsa_error",
    }
    return {k: v for k, v in manifest.items() if k not in _EXCLUDED}


def _anchor_hash(manifest: dict[str, Any], algo: str) -> str:
    return _hash_bytes(canonical_json(_payload_for_hash(manifest)), algo)


def _expected_token(algo: str, anchor_hash: str) -> str:
    return f"{_TOKEN_PREFIX}:{algo}:{anchor_hash}"


def create_file_anchor(
    audit_path: str | Path,
    *,
    anchor_path: str | Path | None = None,
    index_path: str | Path | None = None,
    algo: str = "sha256",
    update_index: bool = True,
    tsa_key_path: str | None = None,
    tsa_token_path: str | Path | None = None,
    external_tsa_url: str | None = None,
) -> FileAnchorResult:
    """Create a local timestamp-anchor manifest for a verified audit JSONL file.

    When ``tsa_key_path`` is provided (an SM2 keyfile), also produce an
    SM2-signed TSA timestamp token (GB/T 32918) binding ``anchor_hash`` to a
    signed UTC time, satisfying the PRD §2.2/§4.5 'SM3 + SM2 + TSA' evidence
    shape. The token is written to ``tsa_token_path`` (default: next to the
    anchor as ``<stem>.tsa.token.json``) and its path + signature algo are
    recorded in the manifest.
    """
    source = Path(audit_path).resolve()
    if not source.exists():
        raise FileNotFoundError(source)

    verify = verify_audit_jsonl(source, algo=algo)
    if not verify["ok"]:
        raise ValueError(f"audit verification failed at line {verify['first_error_line']}")

    records = _read_records(source)
    if not records:
        raise ValueError(f"audit log has no records: {source}")

    created_at = _utc_stamp()
    first = records[0]
    last = records[-1]
    target = Path(anchor_path).resolve() if anchor_path is not None else _default_anchor_path(source, created_at).resolve()
    index = Path(index_path).resolve() if index_path is not None else _default_index_path(target)
    target.parent.mkdir(parents=True, exist_ok=True)

    last_index = _read_last_index_entry(index) if update_index else None
    previous_anchor_hash = last_index.get("anchor_hash", "") if last_index else ""
    anchor_sequence = int(last_index.get("sequence", 0)) + 1 if last_index else 1

    manifest: dict[str, Any] = {
        "version": _VERSION,
        "kind": "local_file_tsa_anchor",
        "created_at": created_at,
        "audit_path": str(source),
        "audit_sha256": _audit_sha256(source),
        "audit_byte_size": source.stat().st_size,
        "audit_hash_algo": algo,
        "record_count": verify["record_count"],
        "first_record_hash": first.get("record_hash", ""),
        "anchored_record_hash": last.get("record_hash", ""),
        "anchored_trace_id": last.get("trace_id", ""),
        "anchor_index_path": str(index),
        "anchor_sequence": anchor_sequence,
        "previous_anchor_hash": previous_anchor_hash,
        "verify": {
            "ok": True,
            "error_count": 0,
            "first_error_line": None,
        },
        "note": "local file anchor for demo/CI evidence; not an external trusted timestamp authority",
    }
    anchor_hash = _anchor_hash(manifest, algo)
    manifest["anchor_hash"] = anchor_hash
    manifest["tsa_token"] = _expected_token(algo, anchor_hash)

    # Optional 国密 SM2 TSA timestamp token (PRD §2.2/§4.5 'SM2 + TSA')
    if tsa_key_path:
        try:
            from xa_guard.audit.tsa_client import (
                create_timestamp_token_with_external,
                write_token,
            )

            prefer_gm = algo == "sm3"
            token = create_timestamp_token_with_external(
                anchor_hash,
                tsa_key_path=tsa_key_path,
                external_tsa_url=external_tsa_url,
                prefer_gm=prefer_gm,
            )
            token_path = (
                Path(tsa_token_path).resolve()
                if tsa_token_path is not None
                else target.parent / f"{target.stem}.tsa.token.json"
            )
            write_token(token, token_path)
            manifest["sm2_tsa_token_path"] = str(token_path)
            manifest["sm2_tsa_signature_algo"] = token.token.get("signature_algo", "")
            manifest["sm2_tsa_utc_time"] = token.token.get("utc_time", "")
        except Exception as exc:  # pragma: no cover - defensive
            manifest["sm2_tsa_error"] = f"{type(exc).__name__}: {exc}"

    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if update_index:
        _append_index_entry(index, manifest, target)
    return FileAnchorResult(audit_path=source, anchor_path=target, manifest=manifest)


def verify_file_anchor(
    audit_path: str | Path,
    anchor_path: str | Path,
    *,
    algo: str | None = None,
    verify_index: bool = False,
) -> FileAnchorResult:
    """Verify that a local file anchor still matches the current audit JSONL."""
    source = Path(audit_path).resolve()
    anchor = Path(anchor_path).resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    if not anchor.exists():
        raise FileNotFoundError(anchor)

    manifest = json.loads(anchor.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError(f"anchor is not a JSON object: {anchor}")
    if manifest.get("version") != _VERSION:
        raise ValueError(f"unsupported anchor version: {manifest.get('version')}")

    hash_algo = algo or manifest.get("audit_hash_algo", "sha256")
    expected_hash = _anchor_hash(manifest, hash_algo)
    if manifest.get("anchor_hash") != expected_hash:
        raise ValueError("anchor_hash mismatch")
    if manifest.get("tsa_token") != _expected_token(hash_algo, expected_hash):
        raise ValueError("tsa_token mismatch")

    verify = verify_audit_jsonl(source, algo=hash_algo)
    if not verify["ok"]:
        raise ValueError(f"audit verification failed at line {verify['first_error_line']}")

    records = _read_records(source)
    if not records:
        raise ValueError(f"audit log has no records: {source}")

    first = records[0]
    last = records[-1]
    checks = {
        "audit_path": str(source),
        "audit_sha256": _audit_sha256(source),
        "audit_byte_size": source.stat().st_size,
        "record_count": verify["record_count"],
        "first_record_hash": first.get("record_hash", ""),
        "anchored_record_hash": last.get("record_hash", ""),
    }
    for key, expected_value in checks.items():
        if manifest.get(key) != expected_value:
            raise ValueError(f"anchor {key} mismatch")

    if verify_index:
        index_path = Path(manifest.get("anchor_index_path", "")).resolve()
        if not index_path.exists():
            raise ValueError(f"anchor index not found: {index_path}")
        found = False
        with index_path.open(encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                if not isinstance(entry, dict):
                    raise ValueError(f"anchor index contains non-object entry: {index_path}")
                if entry.get("anchor_hash") == manifest["anchor_hash"]:
                    found = True
                    if entry.get("previous_anchor_hash", "") != manifest.get("previous_anchor_hash", ""):
                        raise ValueError("anchor index previous_anchor_hash mismatch")
                    if int(entry.get("sequence", 0)) != int(manifest.get("anchor_sequence", 0)):
                        raise ValueError("anchor index sequence mismatch")
                    break
        if not found:
            raise ValueError("anchor not found in index")

    return FileAnchorResult(audit_path=source, anchor_path=anchor, manifest=manifest)
