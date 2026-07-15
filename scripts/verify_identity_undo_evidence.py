"""Verify a sealed XA-Guard Identity + Undo evidence bundle.

The verifier intentionally does not trust summary booleans from the producer.  It
re-hashes every artifact, independently verifies the Gate6 and Effect chains,
checks the cross-system identity/effect links, scans for common secret material,
and finally verifies a strict SM2-with-SM3 signature over the canonical manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from xa_guard.audit.sm_crypto import sm2_key_id, sm2_verify_strict, sm3_hash

SCHEMA_ID = "xa-guard-evidence/v1"
DEFAULT_MANIFEST = "artifact-manifest.json"
DEFAULT_SCHEMA = Path(__file__).resolve().parents[1] / "schemas" / "xa-guard-evidence-v1.schema.json"
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_HEX_128 = re.compile(r"^[0-9a-f]{128}$")
_IMAGE_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_JWT_CANDIDATE = re.compile(
    r"(?<![A-Za-z0-9_-])([A-Za-z0-9_-]{8,})\.([A-Za-z0-9_-]{8,})\.([A-Za-z0-9_-]{8,})(?![A-Za-z0-9_-])"
)
_DSN = re.compile(r"(?i)\b(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?)://[^\s\"'<>]+")
_PEM_PRIVATE = re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----")
_SM2_PRIVATE_LINE = re.compile(r"(?im)^\s*private\s*:\s*[0-9a-f]{64}\s*$")
_ASSIGNMENT_LINE = re.compile(
    r"(?im)^\s*(?:export\s+)?([A-Z][A-Z0-9_.-]*)\s*[:=]\s*([^\r\n#]+)"
)
_PROSE_SECRET = re.compile(
    r"(?i)\b(password|client[ _-]?secret|kek|dsn|database[ _-]?url|"
    r"recovery[ _-]?(?:plaintext|material|payload|data)|private[ _-]?key)\s*(?::|=|\bis\b)\s*"
    r"([^\s,;]+)"
)
_CLI_SECRET = re.compile(
    r"(?i)(--(?:password|client-secret|dsn|database-url|kek))\s+(?:\"([^\"]+)\"|'([^']+)'|([^\s]+))"
)
_REDACTED = {
    "",
    "null",
    "none",
    "redacted",
    "[redacted]",
    "<redacted>",
    "***",
    "xxxxx",
    "excluded",
    "omitted",
    "absent",
    "not",
    "never",
    "not-set",
}


class EvidenceError(RuntimeError):
    """A fail-closed evidence validation error."""


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _load_json(path: Path) -> Any:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant is not allowed: {value}")

    try:
        return json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)
    except Exception as exc:
        raise EvidenceError(f"invalid JSON in {path.name}: {exc}") from exc


def normalize_artifact_path(value: str) -> str:
    """Return a canonical POSIX relative path or reject traversal/Windows aliases."""
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise EvidenceError("artifact path must be a non-empty POSIX relative path")
    if re.match(r"^[A-Za-z]:", value) or ":" in value:
        raise EvidenceError(f"absolute artifact path is forbidden: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise EvidenceError(f"unsafe artifact path: {value!r}")
    reserved = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
    for part in path.parts:
        if part.rstrip(" .") != part or part.split(".", 1)[0].upper() in reserved:
            raise EvidenceError(f"unsafe Windows artifact path: {value!r}")
    normalized = path.as_posix()
    if normalized != value:
        raise EvidenceError(f"artifact path is not canonical: {value!r}")
    return normalized


def _bundle_root(bundle: str | Path) -> Path:
    root = Path(bundle)
    if root.is_symlink():
        raise EvidenceError("evidence bundle root must not be a symlink")
    try:
        resolved = root.resolve(strict=True)
    except FileNotFoundError as exc:
        raise EvidenceError(f"evidence bundle does not exist: {root}") from exc
    if not resolved.is_dir():
        raise EvidenceError(f"evidence bundle is not a directory: {root}")
    return resolved


def resolve_bundle_file(bundle: str | Path, relative_path: str) -> Path:
    root = _bundle_root(bundle)
    normalized = normalize_artifact_path(relative_path)
    current = root
    for part in PurePosixPath(normalized).parts:
        current = current / part
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError as exc:
            raise EvidenceError(f"artifact is missing: {normalized}") from exc
        if current.is_symlink() or stat.S_ISLNK(mode):
            raise EvidenceError(f"symlink is forbidden in evidence bundle: {normalized}")
    try:
        current.resolve(strict=True).relative_to(root)
    except (FileNotFoundError, ValueError) as exc:
        raise EvidenceError(f"artifact escapes evidence bundle: {normalized}") from exc
    if not stat.S_ISREG(os.lstat(current).st_mode):
        raise EvidenceError(f"artifact is not a regular file: {normalized}")
    return current


def enumerate_bundle_files(bundle: str | Path, *, exclude: Iterable[str] = ()) -> list[str]:
    root = _bundle_root(bundle)
    excluded = {normalize_artifact_path(path) for path in exclude}
    files: list[str] = []
    for current, directories, filenames in os.walk(root, topdown=True, followlinks=False):
        base = Path(current)
        for name in list(directories):
            candidate = base / name
            if candidate.is_symlink():
                raise EvidenceError(f"symlink is forbidden in evidence bundle: {candidate.relative_to(root)}")
        for name in filenames:
            candidate = base / name
            relative = candidate.relative_to(root).as_posix()
            normalize_artifact_path(relative)
            mode = os.lstat(candidate).st_mode
            if candidate.is_symlink() or stat.S_ISLNK(mode):
                raise EvidenceError(f"symlink is forbidden in evidence bundle: {relative}")
            if not stat.S_ISREG(mode):
                raise EvidenceError(f"non-regular artifact is forbidden: {relative}")
            if relative not in excluded:
                files.append(relative)
    return sorted(files)


def _normalized_secret_label(label: str) -> str:
    return re.sub(r"[^a-z0-9]", "", label.lower())


def _is_redacted(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        normalized = value.strip().strip("\"'")
        if normalized.lower() in _REDACTED:
            return True
        if normalized.startswith(("$", "${", "env:", "secret-file:")):
            return True
        if len(normalized) > 2 and normalized.startswith("%") and normalized.endswith("%"):
            return True
    return False


def _secret_label_kind(label: str) -> str:
    normalized = _normalized_secret_label(label)
    public_suffixes = ("file", "path", "id", "sha256", "digest", "present", "ciphertext", "nonce", "wrapped")
    if normalized.endswith(public_suffixes):
        return ""
    if normalized.endswith("password"):
        return "password"
    if normalized.endswith("clientsecret"):
        return "client secret"
    if normalized in {"dsn", "databaseurl"} or normalized.endswith("dsn"):
        return "database DSN"
    if "kek" in normalized:
        return "KEK material"
    if normalized == "recovery" or normalized.startswith(
        ("recoveryplaintext", "recoverymaterial", "recoverypayload", "recoverydata")
    ):
        return "recovery plaintext"
    if normalized.endswith("privatekey"):
        return "private key"
    return ""


def _sensitive_json_findings(value: Any, location: str = "$") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        normalized_keys = {_normalized_secret_label(str(key)): key for key in value}
        if "active" in normalized_keys and "keys" in normalized_keys:
            key_value = value[normalized_keys["keys"]]
            if isinstance(key_value, dict) and key_value:
                findings.append(f"{location}: keyring material")
        for key, item in value.items():
            child = f"{location}.{key}"
            kind = _secret_label_kind(str(key))
            if kind and not _is_redacted(item):
                findings.append(f"{child}: non-redacted {kind}")
            findings.extend(_sensitive_json_findings(item, child))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            findings.extend(_sensitive_json_findings(item, f"{location}[{index}]"))
    return findings


def _looks_like_jwt(candidate: str) -> bool:
    import base64

    header_text = candidate.split(".", 1)[0]
    try:
        raw = base64.urlsafe_b64decode(header_text + "=" * (-len(header_text) % 4))
        header = json.loads(raw)
    except Exception:
        return False
    return isinstance(header, dict) and any(key in header for key in ("alg", "typ", "kid"))


def scan_secret_bytes(path: str, data: bytes) -> list[str]:
    """Return secret categories only; never echo the suspected secret value."""
    text = data.decode("utf-8", errors="ignore")
    findings: list[str] = []
    if any(_looks_like_jwt(match.group(0)) for match in _JWT_CANDIDATE.finditer(text)):
        findings.append(f"{path}: JWT-like bearer value")
    if _DSN.search(text):
        findings.append(f"{path}: database DSN")
    if _PEM_PRIVATE.search(text) or _SM2_PRIVATE_LINE.search(text):
        findings.append(f"{path}: private key material")
    for match in _ASSIGNMENT_LINE.finditer(text):
        label = _normalized_secret_label(match.group(1))
        value = match.group(2).strip().strip("\"'")
        if _secret_label_kind(label) and not _is_redacted(value):
            findings.append(f"{path}: non-redacted value assigned to {match.group(1)}")
    for match in _PROSE_SECRET.finditer(text):
        if not _is_redacted(match.group(2)):
            findings.append(f"{path}: non-redacted {match.group(1).lower()}")
    for match in _CLI_SECRET.finditer(text):
        value = next((item for item in match.groups()[1:] if item is not None), "")
        if not _is_redacted(value):
            findings.append(f"{path}: non-redacted value passed to {match.group(1)}")
    suffix = PurePosixPath(path).suffix.lower()
    try:
        if suffix == ".json":
            findings.extend(_sensitive_json_findings(json.loads(text)))
        elif suffix == ".jsonl":
            for line_no, line in enumerate(text.splitlines(), 1):
                if line.strip():
                    findings.extend(_sensitive_json_findings(json.loads(line), f"line[{line_no}]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        # Structural parsers report malformed evidence separately.  Raw scanning
        # still ran and must not be disabled by malformed JSON.
        pass
    return sorted(set(findings))


def scan_bundle_for_secrets(bundle: str | Path, paths: Iterable[str]) -> None:
    findings: list[str] = []
    for relative in paths:
        artifact = resolve_bundle_file(bundle, relative)
        findings.extend(scan_secret_bytes(relative, artifact.read_bytes()))
    if findings:
        raise EvidenceError("secret scan failed: " + "; ".join(sorted(findings)))


def _digest(data: bytes, algorithm: str) -> str:
    if algorithm == "sha256":
        return hashlib.sha256(data).hexdigest()
    if algorithm == "sm3":
        return sm3_hash(data, prefer_gm=True)
    raise EvidenceError(f"unsupported chain hash algorithm: {algorithm}")


def _jsonl_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            record = json.loads(raw)
        except Exception as exc:
            raise EvidenceError(f"invalid JSONL at {path.name}:{line_no}") from exc
        if not isinstance(record, dict):
            raise EvidenceError(f"JSONL record must be an object at {path.name}:{line_no}")
        records.append(record)
    if not records:
        raise EvidenceError(f"chain artifact has no records: {path.name}")
    return records


def verify_gate6_chain(path: Path, algorithm: str) -> list[dict[str, Any]]:
    records = _jsonl_records(path)
    previous = ""
    for line_no, record in enumerate(records, 1):
        if record.get("gen_ai.evidence.hash_prev") != previous:
            raise EvidenceError(f"Gate6 chain predecessor mismatch at line {line_no}")
        unsigned = {key: value for key, value in record.items() if key not in {"record_hash", "signature"}}
        expected = _digest(canonical_json(unsigned), algorithm)
        if record.get("record_hash") != expected:
            raise EvidenceError(f"Gate6 record hash mismatch at line {line_no}")
        previous = expected
    return records


def verify_effect_chain(path: Path, algorithm: str) -> list[dict[str, Any]]:
    if algorithm != "sha256":
        raise EvidenceError("Effect event chain v1 requires sha256")
    records = _jsonl_records(path)
    previous = ""
    previous_seq = -1
    required = {"seq", "tenant_id", "effect_id", "event_type", "actor_sub", "payload", "prev_hash", "record_hash"}
    for line_no, record in enumerate(records, 1):
        if set(record) - (required | {"occurred_at"}) or not required.issubset(record):
            raise EvidenceError(f"Effect chain record shape is invalid at line {line_no}")
        if not isinstance(record["seq"], int) or record["seq"] <= previous_seq:
            raise EvidenceError(f"Effect chain sequence is not increasing at line {line_no}")
        if record["prev_hash"] != previous:
            raise EvidenceError(f"Effect chain predecessor mismatch at line {line_no}")
        hashed = {
            "tenant_id": record["tenant_id"],
            "effect_id": record["effect_id"],
            "event_type": record["event_type"],
            "actor_sub": record["actor_sub"],
            "payload": record["payload"],
            "prev_hash": record["prev_hash"],
        }
        expected = hashlib.sha256(canonical_json(hashed)).hexdigest()
        if record["record_hash"] != expected:
            raise EvidenceError(f"Effect event hash mismatch at line {line_no}")
        previous = expected
        previous_seq = record["seq"]
    return records


def _deep_contains_key_value(value: Any, key: str, expected: str) -> bool:
    if isinstance(value, dict):
        if str(value.get(key, "")) == expected:
            return True
        return any(_deep_contains_key_value(item, key, expected) for item in value.values())
    if isinstance(value, list):
        return any(_deep_contains_key_value(item, key, expected) for item in value)
    return False


def _single_event(records: list[dict[str, Any]], event_type: str, effect_id: str) -> dict[str, Any]:
    matches = [
        record for record in records if record.get("event_type") == event_type and record.get("effect_id") == effect_id
    ]
    if len(matches) != 1:
        raise EvidenceError(f"expected exactly one {event_type!r} event for effect {effect_id!r}")
    return matches[0]


def verify_cross_links(
    bundle: str | Path,
    manifest: dict[str, Any],
    gate6: list[dict[str, Any]],
    effects: list[dict[str, Any]],
) -> None:
    links = manifest["cross_links"]
    effect_id = links["effect_id"]
    action_trace = links["original_trace_id"]
    compensation_trace = links["compensation_trace_id"]
    requester = links["requester_sub"]
    approver = links["approver_sub"]
    tenant = links["tenant_id"]
    agent = links["agent_id"]
    if action_trace == compensation_trace:
        raise EvidenceError("original and compensation traces must be distinct")
    if requester == approver:
        raise EvidenceError("requester and approver must be distinct subjects")

    action_records = [record for record in gate6 if str(record.get("trace_id", "")) == action_trace]
    compensation_records = [record for record in gate6 if str(record.get("trace_id", "")) == compensation_trace]
    if not any(str(record.get("gen_ai.resilience.effect_id", "")) == effect_id for record in action_records):
        raise EvidenceError("original Gate6 trace is not linked to the effect")
    if not any(
        str(record.get("gen_ai.resilience.compensates_effect_id", "")) == effect_id
        for record in compensation_records
    ):
        raise EvidenceError("compensation Gate6 trace is not linked to the original effect")
    if not any(str(record.get("gen_ai.governance.human_principal", "")) == requester for record in action_records):
        raise EvidenceError("original Gate6 trace is not bound to the requester")
    if not any(str(record.get("gen_ai.governance.agent_id", "")) == agent for record in action_records):
        raise EvidenceError("original Gate6 trace is not bound to the assigned agent")
    if not any(
        str(record.get("gen_ai.governance.human_principal", "")) == approver
        for record in compensation_records
    ):
        raise EvidenceError("compensation Gate6 trace is not bound to the approver")
    for record in action_records + compensation_records:
        if str(record.get("gen_ai.governance.tenant_id", "")) != tenant:
            raise EvidenceError("Gate6 trace tenant does not match the sealed tenant")

    prepared = _single_event(effects, "effect_prepared", effect_id)
    requested = _single_event(effects, "undo_requested", effect_id)
    approved = _single_event(effects, "undo_approved", effect_id)
    compensated = _single_event(effects, "compensated", effect_id)
    if prepared["payload"].get("trace_id") != action_trace:
        raise EvidenceError("Effect chain original trace does not match Gate6")
    if prepared["actor_sub"] != requester:
        raise EvidenceError("Effect chain prepared actor does not match the requester")
    if requested["actor_sub"] != requester:
        raise EvidenceError("Effect chain requester does not match the identity link")
    if approved["actor_sub"] != approver:
        raise EvidenceError("Effect chain approver does not match the identity link")
    if compensated["payload"].get("trace_id") != compensation_trace:
        raise EvidenceError("Effect chain compensation trace does not match Gate6")
    request_ids = {
        str(requested["payload"].get("request_id", "")),
        str(approved["payload"].get("request_id", "")),
        str(compensated["payload"].get("request_id", "")),
    }
    if "" in request_ids or len(request_ids) != 1:
        raise EvidenceError("Effect chain undo request ids are not consistently linked")
    if any(record["tenant_id"] != tenant for record in effects):
        raise EvidenceError("Effect chain contains a different tenant")

    business_path = links["business_artifact"]
    business = _load_json(resolve_bundle_file(bundle, business_path))
    if links["business_effect_id"] != effect_id or not _deep_contains_key_value(
        business, "effect_id", effect_id
    ):
        raise EvidenceError("business artifact is not linked to the effect id")

    assignment_path = links["assignment_artifact"]
    assignment_file = resolve_bundle_file(bundle, assignment_path)
    if hashlib.sha256(assignment_file.read_bytes()).hexdigest() != links["assignment_snapshot_sha256"]:
        raise EvidenceError("assignment snapshot hash does not match the cross-link")
    assignment = _load_json(assignment_file)
    if not isinstance(assignment, dict):
        raise EvidenceError("assignment snapshot must be an object")
    for key, expected in {"tenant_id": tenant, "principal_sub": requester, "agent_id": agent}.items():
        if str(assignment.get(key, "")) != expected:
            raise EvidenceError(f"assignment snapshot is not linked by {key}")
    assignment_record = assignment.get("assignment")
    if not isinstance(assignment_record, dict):
        raise EvidenceError("assignment snapshot requires an assignment object")
    if str(assignment_record.get("assignment_id", "")) != links["assignment_id"]:
        raise EvidenceError("assignment snapshot is not linked by assignment_id")
    if assignment_record.get("version") != links["assignment_version"]:
        raise EvidenceError("assignment snapshot version does not match the cross-link")


def _require_exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise EvidenceError(f"{label} keys must be exactly {sorted(expected)}")


def _require_nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceError(f"{label} must be a non-empty string")
    return value


def _require_sorted_unique(items: list[Any], key: str, label: str) -> None:
    values = [item[key] for item in items]
    if values != sorted(values) or len(values) != len(set(values)):
        raise EvidenceError(f"{label} must be sorted by {key} and unique")


def validate_manifest_shape(manifest: Any) -> dict[str, Any]:
    if not isinstance(manifest, dict):
        raise EvidenceError("manifest must be a JSON object")
    _require_exact_keys(
        manifest,
        {"schema", "run", "source", "images", "tools", "artifacts", "chains", "cross_links", "acceptance", "signature"},
        "manifest",
    )
    if manifest["schema"] != SCHEMA_ID:
        raise EvidenceError(f"unsupported manifest schema: {manifest['schema']!r}")

    run = manifest["run"]
    if not isinstance(run, dict):
        raise EvidenceError("run metadata must be an object")
    _require_exact_keys(run, {"id", "mode", "started_at", "completed_at"}, "run")
    for key in ("id", "mode", "started_at", "completed_at"):
        _require_nonempty_string(run[key], f"run.{key}")
    try:
        started = datetime.fromisoformat(run["started_at"].replace("Z", "+00:00"))
        completed = datetime.fromisoformat(run["completed_at"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceError("run timestamps must be ISO-8601") from exc
    if started.tzinfo is None or completed.tzinfo is None or completed < started:
        raise EvidenceError("run timestamps require timezones and completed_at >= started_at")

    source = manifest["source"]
    if not isinstance(source, dict):
        raise EvidenceError("source metadata must be an object")
    _require_exact_keys(source, {"repository", "revision", "dirty"}, "source")
    _require_nonempty_string(source["repository"], "source.repository")
    _require_nonempty_string(source["revision"], "source.revision")
    if not isinstance(source["dirty"], bool):
        raise EvidenceError("source.dirty must be a boolean")

    for label, keys in (("images", {"name", "digest"}), ("tools", {"name", "version"})):
        items = manifest[label]
        if not isinstance(items, list) or not items:
            raise EvidenceError(f"{label} must be a non-empty array")
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise EvidenceError(f"{label}[{index}] must be an object")
            _require_exact_keys(item, keys, f"{label}[{index}]")
            for key in keys:
                _require_nonempty_string(item[key], f"{label}[{index}].{key}")
        _require_sorted_unique(items, "name", label)
    if any(not _IMAGE_DIGEST.fullmatch(item["digest"]) for item in manifest["images"]):
        raise EvidenceError("every image digest must be sha256:<64 lowercase hex>")

    artifacts = manifest["artifacts"]
    if not isinstance(artifacts, list) or not artifacts:
        raise EvidenceError("artifacts must be a non-empty array")
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            raise EvidenceError(f"artifacts[{index}] must be an object")
        _require_exact_keys(artifact, {"path", "bytes", "sha256"}, f"artifacts[{index}]")
        normalize_artifact_path(artifact["path"])
        if not isinstance(artifact["bytes"], int) or artifact["bytes"] < 0:
            raise EvidenceError("artifact byte length must be a non-negative integer")
        if not isinstance(artifact["sha256"], str) or not _HEX_64.fullmatch(artifact["sha256"]):
            raise EvidenceError("artifact sha256 must be 64 lowercase hex")
    _require_sorted_unique(artifacts, "path", "artifacts")

    chains = manifest["chains"]
    if not isinstance(chains, dict):
        raise EvidenceError("chains must be an object")
    _require_exact_keys(chains, {"gate6", "effect"}, "chains")
    for name, algorithms in (("gate6", {"sha256", "sm3"}), ("effect", {"sha256"})):
        chain = chains[name]
        if not isinstance(chain, dict):
            raise EvidenceError(f"chains.{name} must be an object")
        _require_exact_keys(chain, {"path", "algorithm", "records"}, f"chains.{name}")
        normalize_artifact_path(chain["path"])
        if chain["algorithm"] not in algorithms:
            raise EvidenceError(f"unsupported chains.{name}.algorithm")
        if not isinstance(chain["records"], int) or chain["records"] <= 0:
            raise EvidenceError(f"chains.{name}.records must be positive")

    links = manifest["cross_links"]
    if not isinstance(links, dict):
        raise EvidenceError("cross_links must be an object")
    link_keys = {
        "tenant_id", "agent_id", "effect_id", "original_trace_id", "compensation_trace_id",
        "requester_sub", "approver_sub", "business_effect_id", "business_artifact",
        "assignment_artifact", "assignment_snapshot_sha256", "assignment_id", "assignment_version",
    }
    _require_exact_keys(links, link_keys, "cross_links")
    for key in link_keys - {"assignment_version"}:
        _require_nonempty_string(links[key], f"cross_links.{key}")
    normalize_artifact_path(links["business_artifact"])
    normalize_artifact_path(links["assignment_artifact"])
    if not _HEX_64.fullmatch(links["assignment_snapshot_sha256"]):
        raise EvidenceError("assignment_snapshot_sha256 must be 64 lowercase hex")
    if not isinstance(links["assignment_version"], int) or links["assignment_version"] <= 0:
        raise EvidenceError("assignment_version must be positive")

    acceptance = manifest["acceptance"]
    if not isinstance(acceptance, dict):
        raise EvidenceError("acceptance must be an object")
    _require_exact_keys(acceptance, {"assertions", "boundaries"}, "acceptance")
    assertions = acceptance["assertions"]
    boundaries = acceptance["boundaries"]
    if not isinstance(assertions, list) or not assertions:
        raise EvidenceError("acceptance.assertions must be non-empty")
    if not isinstance(boundaries, list) or not boundaries:
        raise EvidenceError("acceptance.boundaries must be non-empty")
    for index, assertion in enumerate(assertions):
        if not isinstance(assertion, dict):
            raise EvidenceError(f"assertions[{index}] must be an object")
        _require_exact_keys(assertion, {"id", "statement", "passed", "evidence"}, f"assertions[{index}]")
        _require_nonempty_string(assertion["id"], "assertion.id")
        _require_nonempty_string(assertion["statement"], "assertion.statement")
        if not isinstance(assertion["passed"], bool):
            raise EvidenceError("assertion.passed must be boolean")
        if not isinstance(assertion["evidence"], list) or not assertion["evidence"]:
            raise EvidenceError("assertion.evidence must be a non-empty array")
        paths = [normalize_artifact_path(path) for path in assertion["evidence"]]
        if paths != sorted(paths) or len(paths) != len(set(paths)):
            raise EvidenceError("assertion evidence paths must be sorted and unique")
    _require_sorted_unique(assertions, "id", "acceptance.assertions")
    for index, boundary in enumerate(boundaries):
        if not isinstance(boundary, dict):
            raise EvidenceError(f"boundaries[{index}] must be an object")
        _require_exact_keys(boundary, {"id", "statement"}, f"boundaries[{index}]")
        _require_nonempty_string(boundary["id"], "boundary.id")
        _require_nonempty_string(boundary["statement"], "boundary.statement")
    _require_sorted_unique(boundaries, "id", "acceptance.boundaries")

    signature = manifest["signature"]
    if not isinstance(signature, dict):
        raise EvidenceError("signature must be an object")
    _require_exact_keys(signature, {"algorithm", "key_id", "public_key", "value"}, "signature")
    if signature["algorithm"] != "SM2-with-SM3":
        raise EvidenceError("only strict SM2-with-SM3 manifest signatures are accepted")
    if not isinstance(signature["key_id"], str) or not re.fullmatch(r"[0-9a-f]{16}", signature["key_id"]):
        raise EvidenceError("signature key_id must be 16 lowercase hex")
    if not isinstance(signature["public_key"], str) or not _HEX_128.fullmatch(signature["public_key"]):
        raise EvidenceError("signature public_key must be a 128-hex SM2 point")
    if not isinstance(signature["value"], str) or not _HEX_128.fullmatch(signature["value"]):
        raise EvidenceError("signature value must be a 128-hex SM2 signature")
    return manifest


def validate_against_json_schema(manifest: dict[str, Any], schema_path: str | Path = DEFAULT_SCHEMA) -> None:
    schema_file = Path(schema_path)
    if not schema_file.is_file():
        raise EvidenceError(f"evidence schema is missing: {schema_file}")
    schema = _load_json(schema_file)
    try:
        import jsonschema
    except ImportError:
        return
    try:
        jsonschema.Draft202012Validator(schema).validate(manifest)
    except jsonschema.ValidationError as exc:
        raise EvidenceError(f"manifest JSON Schema validation failed: {exc.message}") from exc


def verify_artifacts(bundle: str | Path, manifest: dict[str, Any], manifest_name: str) -> None:
    declared = [artifact["path"] for artifact in manifest["artifacts"]]
    actual = enumerate_bundle_files(bundle, exclude=[manifest_name])
    if declared != actual:
        missing = sorted(set(declared) - set(actual))
        extra = sorted(set(actual) - set(declared))
        raise EvidenceError(f"artifact set mismatch (missing={missing}, extra={extra})")
    for artifact in manifest["artifacts"]:
        data = resolve_bundle_file(bundle, artifact["path"]).read_bytes()
        if len(data) != artifact["bytes"]:
            raise EvidenceError(f"artifact byte length mismatch: {artifact['path']}")
        if hashlib.sha256(data).hexdigest() != artifact["sha256"]:
            raise EvidenceError(f"artifact SHA-256 mismatch: {artifact['path']}")


def verify_acceptance(manifest: dict[str, Any]) -> None:
    artifacts = {artifact["path"] for artifact in manifest["artifacts"]}
    failed = [assertion["id"] for assertion in manifest["acceptance"]["assertions"] if not assertion["passed"]]
    if failed:
        raise EvidenceError(f"acceptance assertions are not all passing: {failed}")
    for assertion in manifest["acceptance"]["assertions"]:
        unknown = sorted(set(assertion["evidence"]) - artifacts)
        if unknown:
            raise EvidenceError(f"assertion {assertion['id']!r} cites undeclared artifacts: {unknown}")


def verify_chains_and_links(bundle: str | Path, manifest: dict[str, Any]) -> dict[str, int]:
    gate_descriptor = manifest["chains"]["gate6"]
    effect_descriptor = manifest["chains"]["effect"]
    gate6 = verify_gate6_chain(
        resolve_bundle_file(bundle, gate_descriptor["path"]), gate_descriptor["algorithm"]
    )
    effects = verify_effect_chain(
        resolve_bundle_file(bundle, effect_descriptor["path"]), effect_descriptor["algorithm"]
    )
    if len(gate6) != gate_descriptor["records"]:
        raise EvidenceError("Gate6 record count does not match the manifest")
    if len(effects) != effect_descriptor["records"]:
        raise EvidenceError("Effect event count does not match the manifest")
    verify_cross_links(bundle, manifest, gate6, effects)
    return {"gate6_records": len(gate6), "effect_records": len(effects)}


def unsigned_manifest_bytes(manifest: dict[str, Any]) -> bytes:
    unsigned = dict(manifest)
    signature = dict(unsigned.get("signature") or {})
    signature.pop("value", None)
    unsigned["signature"] = signature
    return canonical_json(unsigned)


def verify_manifest_signature(manifest: dict[str, Any], expected_key_id: str = "") -> None:
    signature = manifest["signature"]
    public_key = signature["public_key"]
    if expected_key_id and signature["key_id"] != expected_key_id:
        raise EvidenceError("manifest signer key_id does not match the independently pinned key id")
    with tempfile.TemporaryDirectory(prefix="xa-evidence-public-") as temp_dir:
        public_path = Path(temp_dir) / "public.key"
        public_path.write_text(f"public: {public_key}\n", encoding="utf-8")
        expected_key_id = sm2_key_id(str(public_path))
        if signature["key_id"] != expected_key_id:
            raise EvidenceError("SM2 public key does not match signature key_id")
        try:
            valid = sm2_verify_strict(unsigned_manifest_bytes(manifest), signature["value"], str(public_path))
        except Exception as exc:
            raise EvidenceError(f"strict SM2-with-SM3 verification failed: {exc}") from exc
    if not valid:
        raise EvidenceError("manifest SM2-with-SM3 signature is invalid")


def verify_bundle(
    bundle: str | Path,
    *,
    manifest_name: str = DEFAULT_MANIFEST,
    schema_path: str | Path = DEFAULT_SCHEMA,
    expected_key_id: str = "",
) -> dict[str, Any]:
    normalize_artifact_path(manifest_name)
    manifest_path = resolve_bundle_file(bundle, manifest_name)
    manifest = validate_manifest_shape(_load_json(manifest_path))
    validate_against_json_schema(manifest, schema_path)
    verify_manifest_signature(manifest, expected_key_id)
    manifest_findings = scan_secret_bytes(manifest_name, manifest_path.read_bytes())
    if manifest_findings:
        raise EvidenceError("manifest secret scan failed: " + "; ".join(manifest_findings))
    verify_artifacts(bundle, manifest, manifest_name)
    paths = [artifact["path"] for artifact in manifest["artifacts"]]
    scan_bundle_for_secrets(bundle, paths)
    verify_acceptance(manifest)
    counts = verify_chains_and_links(bundle, manifest)
    return {
        "ok": True,
        "schema": manifest["schema"],
        "run_id": manifest["run"]["id"],
        "artifact_count": len(paths),
        **counts,
        "signature_algorithm": manifest["signature"]["algorithm"],
        "signature_key_id": manifest["signature"]["key_id"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify XA-Guard Identity + Undo evidence")
    parser.add_argument("--bundle", required=True, help="sealed evidence bundle directory")
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST, help="manifest path relative to bundle")
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA), help="xa-guard-evidence/v1 JSON Schema")
    parser.add_argument("--expected-key-id", default="", help="optional independently pinned signer key id")
    args = parser.parse_args(argv)
    try:
        result = verify_bundle(
            args.bundle,
            manifest_name=args.manifest,
            schema_path=args.schema,
            expected_key_id=args.expected_key_id,
        )
    except EvidenceError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
