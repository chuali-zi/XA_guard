"""Audit log rotation/archive helpers.

Archived logs are evidence. This module moves the original JSONL bytes aside
and writes a manifest instead of rewriting broken records.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from xa_guard.audit.merkle import audit_file_lock, canonical_json, compute_record_hash
from xa_guard.audit.external_signer import verify_with_external_command
from xa_guard.audit.sm_crypto import (
    hmac_demo_key_id,
    sm2_key_id,
    sm2_verify,
    sm2_verify_strict,
)

_HASH_PREV_KEY = "gen_ai.evidence.hash_prev"
_RECORD_HASH_KEY = "record_hash"


def _reject_nonfinite(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is not allowed: {value}")


@dataclass(frozen=True)
class ArchiveResult:
    archive_path: Path
    manifest_path: Path
    manifest: dict[str, Any]


def _unique_archive_path(source: Path, archive_dir: Path, archived_at: datetime) -> Path:
    stamp = archived_at.strftime("%Y%m%dT%H%M%S%fZ")
    candidate = archive_dir / f"{source.stem}-{stamp}{source.suffix}"
    if not candidate.exists():
        return candidate
    for suffix in range(1, 1000):
        candidate = archive_dir / f"{source.stem}-{stamp}-{suffix}{source.suffix}"
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"could not allocate unique archive path in {archive_dir}")


def verify_audit_jsonl(path: str | Path, *, algo: str = "sha256") -> dict[str, Any]:
    """Verify audit JSONL and count every line with a parse, chain, or hash error."""
    audit_path = Path(path)
    prev_hash = ""
    record_count = 0
    error_count = 0
    first_error_line: int | None = None

    with audit_path.open(encoding="utf-8") as handle:
        for line_no, raw_line in enumerate(handle, 1):
            line = raw_line.strip()
            if not line:
                continue

            record_count += 1
            line_has_error = False
            try:
                record = json.loads(line, parse_constant=_reject_nonfinite)
            except Exception:
                record = None
                line_has_error = True
            else:
                if record.get(_HASH_PREV_KEY, "") != prev_hash:
                    line_has_error = True
                if record.get(_RECORD_HASH_KEY, "") != compute_record_hash(record, algo):
                    line_has_error = True

            if line_has_error:
                error_count += 1
                if first_error_line is None:
                    first_error_line = line_no

            if isinstance(record, dict):
                prev_hash = record.get(_RECORD_HASH_KEY, "") or ""

    return {
        "ok": error_count == 0,
        "record_count": record_count,
        "error_count": error_count,
        "first_error_line": first_error_line,
    }


def verify_audit_signatures(
    path: str | Path,
    *,
    mode: str,
    key_path: str = "",
    external_verify_command: str | list[str] | tuple[str, ...] | None = None,
    external_key_id: str = "",
    external_algorithm: str = "EXTERNAL-HSM-SM2-SM3",
    external_provider: str = "",
    external_timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    """Verify every audit record signature in strict SM2 or explicit demo mode."""
    normalized_mode = mode.lower()
    if normalized_mode == "sm2":
        expected_algorithm = "SM2-SM3"
        expected_key_id = sm2_key_id(key_path)

        def verifier(payload: bytes, signature: str) -> bool:
            return sm2_verify_strict(payload, signature, key_path)
    elif normalized_mode == "hmac-demo":
        expected_algorithm = "HMAC-SHA256-DEMO"
        expected_key_id = hmac_demo_key_id(key_path)

        def verifier(payload: bytes, signature: str) -> bool:
            return sm2_verify(payload, signature, key_path, prefer_gm=False)
    elif normalized_mode == "external":
        if not external_verify_command:
            raise ValueError("external signature verification requires external_verify_command")
        if not external_key_id:
            raise ValueError("external signature verification requires external_key_id")
        expected_algorithm = external_algorithm
        expected_key_id = external_key_id

        def verifier(payload: bytes, signature: str) -> bool:
            return verify_with_external_command(
                payload,
                signature,
                command=external_verify_command,
                key_id=external_key_id,
                algorithm=external_algorithm,
                provider=external_provider,
                timeout_seconds=external_timeout_seconds,
            )
    else:
        raise ValueError(f"unsupported signature verification mode: {mode}")

    record_count = 0
    error_count = 0
    first_error_line: int | None = None
    with Path(path).open(encoding="utf-8") as handle:
        for line_no, raw_line in enumerate(handle, 1):
            line = raw_line.strip()
            if not line:
                continue
            record_count += 1
            try:
                record = json.loads(line, parse_constant=_reject_nonfinite)
                signature = str(record.pop("signature"))
                valid = (
                    record.get("signature_algorithm") == expected_algorithm
                    and record.get("signature_key_id") == expected_key_id
                    and verifier(canonical_json(record), signature)
                )
            except Exception:
                valid = False
            if not valid:
                error_count += 1
                if first_error_line is None:
                    first_error_line = line_no
    return {
        "ok": record_count > 0 and error_count == 0,
        "mode": normalized_mode,
        "record_count": record_count,
        "error_count": error_count,
        "first_error_line": first_error_line,
        "expected_algorithm": expected_algorithm,
        "expected_key_id": expected_key_id,
    }


def archive_audit_log(
    audit_path: str | Path = "logs/audit/audit.jsonl",
    *,
    archive_dir: str | Path | None = None,
    reason: str = "rotation",
    algo: str = "sha256",
    create_empty: bool = False,
) -> ArchiveResult:
    """Move an audit JSONL to archive and write metadata without rewriting it."""
    source = Path(audit_path)
    target_dir = Path(archive_dir) if archive_dir is not None else source.parent / "archive"

    with audit_file_lock(source):
        if not source.exists():
            raise FileNotFoundError(source)

        archived_at = datetime.now(timezone.utc)
        target_dir.mkdir(parents=True, exist_ok=True)
        archive_path = _unique_archive_path(source, target_dir, archived_at)
        verify = verify_audit_jsonl(source, algo=algo)
        source_size = source.stat().st_size
        source.replace(archive_path)
        if create_empty:
            source.touch()

    manifest_path = archive_path.with_suffix(archive_path.suffix + ".manifest.json")
    manifest: dict[str, Any] = {
        "source_path": str(source),
        "archive_path": str(archive_path),
        "manifest_path": str(manifest_path),
        "archived_at": archived_at.isoformat().replace("+00:00", "Z"),
        "reason": reason,
        "record_count": verify["record_count"],
        "verify": {
            "ok": verify["ok"],
            "error_count": verify["error_count"],
            "first_error_line": verify["first_error_line"],
            "algo": algo,
        },
        "source_size_bytes": source_size,
        "note": "original JSONL bytes preserved; broken chains are not rewritten",
    }
    manifest_payload = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    manifest_path.write_text(manifest_payload, encoding="utf-8")
    return ArchiveResult(archive_path=archive_path, manifest_path=manifest_path, manifest=manifest)
