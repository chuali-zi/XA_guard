"""Static exchange adapter for externally generated CycloneDX 1.6 BOMs.

This module never discovers, downloads, or executes generators.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from xa_guard.aibom.schema_validator import SchemaValidationResult, validate_cyclonedx

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_DEFAULT_MAX_BYTES = 16 * 1024 * 1024


class ExternalGeneratorError(ValueError):
    """Raised when provenance or external output fails closed validation."""


@dataclass(frozen=True)
class ExternalGeneratorSpec:
    """Caller-verified generator identity and invocation record."""

    name: str
    source: str
    version: str
    license_expression: str
    commands: tuple[tuple[str, ...], ...]

    def __post_init__(self) -> None:
        fields = {
            "name": self.name,
            "source": self.source,
            "version": self.version,
            "license_expression": self.license_expression,
        }
        for field_name, value in fields.items():
            if not isinstance(value, str) or not value.strip():
                raise ExternalGeneratorError(f"generator {field_name} must be explicit and non-empty")
        if not isinstance(self.commands, tuple) or not self.commands:
            raise ExternalGeneratorError("generator commands must be a non-empty tuple of argument vectors")
        for index, command in enumerate(self.commands):
            if (
                not isinstance(command, tuple)
                or not command
                or any(not isinstance(argument, str) or not argument for argument in command)
            ):
                raise ExternalGeneratorError(
                    f"generator commands[{index}] must be a non-empty tuple of non-empty strings"
                )

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "source": self.source,
            "version": self.version,
            "license": self.license_expression,
            "commands": [list(command) for command in self.commands],
        }


@dataclass(frozen=True)
class ExternalBomExchange:
    bom: dict[str, Any]
    sha256: str
    generator: ExternalGeneratorSpec
    schema_validation: SchemaValidationResult


def load_external_cyclonedx(
    output: bytes | Path,
    *,
    expected_sha256: str,
    generator: ExternalGeneratorSpec,
    max_bytes: int = _DEFAULT_MAX_BYTES,
) -> ExternalBomExchange:
    """Verify and parse an existing external CycloneDX 1.6 JSON output."""
    if not isinstance(generator, ExternalGeneratorSpec):
        raise ExternalGeneratorError("generator must be an ExternalGeneratorSpec")
    if not isinstance(expected_sha256, str) or not _SHA256_RE.fullmatch(expected_sha256):
        raise ExternalGeneratorError("expected_sha256 must be exactly 64 hexadecimal characters")
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 1:
        raise ExternalGeneratorError("max_bytes must be a positive integer")

    raw = _read_output(output, max_bytes=max_bytes)
    actual_sha256 = hashlib.sha256(raw).hexdigest()
    if not hmac.compare_digest(actual_sha256, expected_sha256.lower()):
        raise ExternalGeneratorError(
            f"external output SHA-256 mismatch: expected {expected_sha256.lower()}, got {actual_sha256}"
        )

    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ExternalGeneratorError("external output is not valid UTF-8 JSON") from exc
    try:
        bom = json.loads(decoded, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, ExternalGeneratorError) as exc:
        raise ExternalGeneratorError(f"external output is not valid JSON: {exc}") from exc
    if not isinstance(bom, dict):
        raise ExternalGeneratorError("external output JSON root must be an object")
    if bom.get("specVersion") != "1.6":
        raise ExternalGeneratorError("external output must declare CycloneDX specVersion ''1.6''")

    validation = validate_cyclonedx(bom)
    if not validation.valid:
        raise ExternalGeneratorError(
            "external output failed CycloneDX schema validation: " + "; ".join(validation.errors)
        )
    return ExternalBomExchange(bom, actual_sha256, generator, validation)


def _read_output(output: bytes | Path, *, max_bytes: int) -> bytes:
    if isinstance(output, bytes):
        raw = output
    elif isinstance(output, Path):
        try:
            size = output.stat().st_size
            if size > max_bytes:
                raise ExternalGeneratorError(
                    f"external output exceeds max_bytes ({size} > {max_bytes})"
                )
            raw = output.read_bytes()
        except ExternalGeneratorError:
            raise
        except OSError as exc:
            raise ExternalGeneratorError(f"cannot read external output: {exc}") from exc
    else:
        raise ExternalGeneratorError("output must be bytes or pathlib.Path")
    if len(raw) > max_bytes:
        raise ExternalGeneratorError(f"external output exceeds max_bytes ({len(raw)} > {max_bytes})")
    return raw


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ExternalGeneratorError(f"duplicate JSON object key {key!r}")
        result[key] = value
    return result
