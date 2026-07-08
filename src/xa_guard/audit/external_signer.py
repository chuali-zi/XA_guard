"""External signer bridge for production HSM/KMS integrations.

The bridge is intentionally small and strict. XA-Guard sends canonical payload
bytes to an operator-provided command over stdin as JSON, and expects JSON on
stdout. The command can be a real HSM/KMS SDK wrapper; this module does not
fabricate a signature when the command is absent or returns malformed output.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from typing import Any


class ExternalSignerError(RuntimeError):
    """Raised when an external signer/ verifier cannot produce trusted output."""


@dataclass(frozen=True)
class ExternalSignature:
    signature: str
    key_id: str
    algorithm: str
    provider: str = ""


def _command_argv(command: str | list[str] | tuple[str, ...]) -> list[str]:
    if isinstance(command, str):
        if not command.strip():
            raise ExternalSignerError("external signer command is empty")
        return shlex.split(command, posix=(os.name != "nt"))
    if isinstance(command, (list, tuple)) and command and all(isinstance(item, str) and item for item in command):
        return list(command)
    raise ExternalSignerError("external signer command must be a non-empty string or argument vector")


def _run_json_command(
    command: str | list[str] | tuple[str, ...],
    request: dict[str, Any],
    *,
    timeout_seconds: float,
) -> dict[str, Any]:
    argv = _command_argv(command)
    try:
        proc = subprocess.run(
            argv,
            input=json.dumps(request, ensure_ascii=False, sort_keys=True),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout_seconds,
            check=False,
        )
    except Exception as exc:
        raise ExternalSignerError(f"external signer command failed to start: {type(exc).__name__}: {exc}") from exc
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        raise ExternalSignerError(f"external signer command exited {proc.returncode}: {stderr}")
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise ExternalSignerError(f"external signer returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ExternalSignerError("external signer JSON response must be an object")
    return payload


def sign_with_external_command(
    payload: bytes,
    *,
    command: str | list[str] | tuple[str, ...],
    key_id: str,
    algorithm: str = "EXTERNAL-HSM-SM2-SM3",
    provider: str = "",
    timeout_seconds: float = 10.0,
) -> ExternalSignature:
    """Sign canonical audit payload bytes with an operator-provided command."""
    if not key_id:
        raise ExternalSignerError("external signer key_id is required")
    request = {
        "operation": "sign",
        "payload_hex": payload.hex(),
        "algorithm": algorithm,
        "key_id": key_id,
        "provider": provider,
    }
    response = _run_json_command(command, request, timeout_seconds=timeout_seconds)
    signature = str(response.get("signature") or "")
    if not signature:
        raise ExternalSignerError("external signer response has no signature")
    response_key_id = str(response.get("key_id") or key_id)
    if response_key_id != key_id:
        raise ExternalSignerError(f"external signer key_id mismatch: expected {key_id}, got {response_key_id}")
    response_algorithm = str(response.get("algorithm") or algorithm)
    if response_algorithm != algorithm:
        raise ExternalSignerError(
            f"external signer algorithm mismatch: expected {algorithm}, got {response_algorithm}"
        )
    return ExternalSignature(
        signature=signature,
        key_id=key_id,
        algorithm=algorithm,
        provider=str(response.get("provider") or provider),
    )


def verify_with_external_command(
    payload: bytes,
    signature: str,
    *,
    command: str | list[str] | tuple[str, ...],
    key_id: str,
    algorithm: str = "EXTERNAL-HSM-SM2-SM3",
    provider: str = "",
    timeout_seconds: float = 10.0,
) -> bool:
    """Verify an external signature through an operator-provided command."""
    if not key_id:
        raise ExternalSignerError("external verifier key_id is required")
    request = {
        "operation": "verify",
        "payload_hex": payload.hex(),
        "signature": signature,
        "algorithm": algorithm,
        "key_id": key_id,
        "provider": provider,
    }
    response = _run_json_command(command, request, timeout_seconds=timeout_seconds)
    if str(response.get("key_id") or key_id) != key_id:
        return False
    if str(response.get("algorithm") or algorithm) != algorithm:
        return False
    return bool(response.get("valid"))
