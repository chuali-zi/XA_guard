"""Collect a secret-free Identity + Undo evidence staging bundle.

The collector reads the running reference PostgreSQL through the existing
``docker compose exec psql`` helper.  It never reads a database connection
string and deliberately projects only public columns.  The resulting directory
is an input to :mod:`seal_identity_undo_evidence`; it is not sealed by this
command.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import subprocess
import sys
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.reference.yml"

try:
    from scripts.verify_identity_undo_evidence import (
        EvidenceError,
        canonical_json,
        enumerate_bundle_files,
        normalize_artifact_path,
        scan_bundle_for_secrets,
        scan_secret_bytes,
        verify_effect_chain,
        verify_gate6_chain,
    )
except ModuleNotFoundError:  # pragma: no cover - direct ``python scripts/...`` execution
    from verify_identity_undo_evidence import (  # type: ignore[no-redef]
        EvidenceError,
        canonical_json,
        enumerate_bundle_files,
        normalize_artifact_path,
        scan_bundle_for_secrets,
        scan_secret_bytes,
        verify_effect_chain,
        verify_gate6_chain,
    )


class CollectionError(RuntimeError):
    """Evidence could not be collected without weakening its claims."""


SqlQuery = Callable[[str], str]
CommandRunner = Callable[[list[str]], str]

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9._:-]{1,160}$")
_SHA256 = re.compile(r"^(?:sha256:)?([0-9a-f]{64})$")
_SENSITIVE_KEY_PARTS = {
    "authorization",
    "approvaltoken",
    "bearer",
    "clientsecret",
    "cookie",
    "databaseurl",
    "dsn",
    "kek",
    "password",
    "privatekey",
    "recovery",
    "secret",
    "session",
    "token",
    "wrappeddek",
}

_EFFECT_FIELDS = (
    "effect_id",
    "tenant_id",
    "trace_id",
    "principal_sub",
    "principal_username",
    "agent_id",
    "data_domain",
    "tool_name",
    "args_sha256",
    "contract_version",
    "contract_hash",
    "side_effect_level",
    "reversibility",
    "status",
    "prepared_at",
    "completed_at",
    "undo_expires_at",
    "result_sha256",
    "downstream_reference",
    "compensation_trace_id",
    "retry_count",
    "last_error_code",
    "authorization_snapshot",
)
_UNDO_FIELDS = (
    "request_id",
    "effect_id",
    "tenant_id",
    "idempotency_sha256",
    "requester_sub",
    "requester_username",
    "reason_sha256",
    "status",
    "approver_sub",
    "approver_username",
    "decision_reason_sha256",
    "compensation_args_sha256",
    "requested_at",
    "decided_at",
)
_BUSINESS_FIELDS = (
    "ticket_id",
    "tenant_id",
    "state",
    "create_effect_id",
    "correlation_id",
    "created_at",
    "cancelled_at",
)


def _reference_sql(query: str) -> str:
    """Import the Compose psql helper lazily so unit collection stays offline."""

    try:
        from scripts.reference_acceptance_lib import sql as reference_sql
    except ModuleNotFoundError:  # pragma: no cover - direct script execution
        scripts_directory = str(ROOT / "scripts")
        if scripts_directory not in sys.path:
            sys.path.insert(0, scripts_directory)
        from reference_acceptance_lib import sql as reference_sql  # type: ignore[no-redef]
    return reference_sql(query)


def _run_command(args: list[str]) -> str:
    completed = subprocess.run(
        args,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return completed.stdout.strip()


def _safe_identifier(value: str, label: str) -> str:
    if not _SAFE_IDENTIFIER.fullmatch(value):
        raise CollectionError(f"{label} has an unsafe format")
    return value


def _literal(value: str) -> str:
    # Values have already passed _safe_identifier; doubling remains defense in depth.
    return "'" + value.replace("'", "''") + "'"


def _load_sql_json(query: str, query_sql: SqlQuery) -> Any:
    raw = query_sql(query).strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise CollectionError("reference database returned malformed JSON evidence") from exc


def _one_public_row(
    table: str,
    fields: tuple[str, ...],
    where: str,
    order: str,
    marker: str,
    query_sql: SqlQuery,
) -> dict[str, Any]:
    columns = ",".join(fields)
    query = (
        f"/* evidence:{marker} */ SELECT row_to_json(public_row)::text FROM "
        f"(SELECT {columns} FROM {table} WHERE {where} ORDER BY {order} LIMIT 1) public_row"
    )
    value = _load_sql_json(query, query_sql)
    if not isinstance(value, dict):
        raise CollectionError(f"required {marker} row is absent")
    # Never trust a mocked or future SQL adapter to honor the projection.
    return {field: value.get(field) for field in fields}


def _select_effect(effect_id: str, query_sql: SqlQuery) -> dict[str, Any]:
    where = "status='compensated'"
    if effect_id:
        where += f" AND effect_id={_literal(_safe_identifier(effect_id, 'effect id'))}"
    return _one_public_row(
        "xa_effects",
        _EFFECT_FIELDS,
        where,
        "prepared_at DESC,effect_id DESC",
        "effect",
        query_sql,
    )


def _select_undo(effect_id: str, tenant_id: str, query_sql: SqlQuery) -> dict[str, Any]:
    where = f"effect_id={_literal(effect_id)} AND tenant_id={_literal(tenant_id)} AND status='completed'"
    return _one_public_row(
        "xa_undo_requests",
        _UNDO_FIELDS,
        where,
        "decided_at DESC,request_id DESC",
        "undo",
        query_sql,
    )


def _select_business(effect_id: str, tenant_id: str, query_sql: SqlQuery) -> dict[str, Any]:
    where = f"create_effect_id={_literal(effect_id)} AND tenant_id={_literal(tenant_id)}"
    return _one_public_row(
        "xa_reference_tickets",
        _BUSINESS_FIELDS,
        where,
        "created_at DESC,ticket_id DESC",
        "business",
        query_sql,
    )


def _select_effect_events(effect_id: str, tenant_id: str, query_sql: SqlQuery) -> list[dict[str, Any]]:
    query = f"""
/* evidence:effect-events */
SELECT COALESCE(json_agg(public_row ORDER BY seq),'[]'::json)::text
FROM (
  SELECT seq,tenant_id,effect_id,event_type,actor_sub,occurred_at,payload,prev_hash,record_hash
  FROM xa_effect_events
  WHERE tenant_id={_literal(tenant_id)}
    AND seq <= (
      SELECT max(seq) FROM xa_effect_events
      WHERE tenant_id={_literal(tenant_id)} AND effect_id={_literal(effect_id)}
        AND event_type='compensated'
    )
) public_row
"""
    value = _load_sql_json(query, query_sql)
    if not isinstance(value, list) or not value or not all(isinstance(row, dict) for row in value):
        raise CollectionError("tenant Effect event chain is absent or malformed")
    return value


def _select_gate6_rows(
    tenant_id: str,
    original_trace: str,
    compensation_trace: str,
    query_sql: SqlQuery,
) -> list[dict[str, Any]]:
    traces = f"{_literal(original_trace)},{_literal(compensation_trace)}"
    query = f"""
/* evidence:gate6 */
SELECT COALESCE(json_agg(public_row ORDER BY seq),'[]'::json)::text
FROM (
  SELECT seq,tenant_id,trace_id,record,prev_hash,record_hash,source_instance,occurred_at
  FROM xa_gate6_events
  WHERE tenant_id={_literal(tenant_id)}
    AND seq <= (
      SELECT max(seq) FROM xa_gate6_events
      WHERE tenant_id={_literal(tenant_id)} AND trace_id IN ({traces})
    )
) public_row
"""
    value = _load_sql_json(query, query_sql)
    if not isinstance(value, list) or not value or not all(isinstance(row, dict) for row in value):
        raise CollectionError("tenant Gate6 chain is absent or malformed")
    return value


def _normalized_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _is_sensitive_key(key: str) -> bool:
    normalized = _normalized_key(key)
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def _public_projection(value: Any) -> Any:
    """Remove replayable credentials and secret-looking scalars recursively."""

    if isinstance(value, dict):
        return {
            str(key): _public_projection(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if not _is_sensitive_key(str(key))
            and str(key) not in {"record_hash", "signature", "signature_algorithm", "signature_key_id"}
        }
    if isinstance(value, list):
        return [_public_projection(item) for item in value]
    if isinstance(value, str) and scan_secret_bytes("gate6-value.txt", value.encode("utf-8")):
        return "[excluded]"
    return value


def _gate6_projection(
    rows: list[dict[str, Any]], original_trace: str, compensation_trace: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    previous_source = ""
    previous_public = ""
    public_records: list[dict[str, Any]] = []
    mapping: list[dict[str, Any]] = []
    traces_seen: set[str] = set()
    for row in rows:
        record = row.get("record")
        if not isinstance(record, dict):
            raise CollectionError("Gate6 database row has no record object")
        source_hash = str(row.get("record_hash") or "")
        if str(row.get("prev_hash") or "") != previous_source:
            raise CollectionError("durable Gate6 source chain predecessor mismatch")
        source_unsigned = {
            key: item for key, item in record.items() if key not in {"record_hash", "signature"}
        }
        if hashlib.sha256(canonical_json(source_unsigned)).hexdigest() != source_hash:
            raise CollectionError("durable Gate6 source record hash mismatch")
        if str(record.get("record_hash") or "") != source_hash:
            raise CollectionError("Gate6 row and embedded record hashes differ")
        if str(record.get("gen_ai.evidence.hash_prev") or "") != previous_source:
            raise CollectionError("Gate6 embedded predecessor differs from its durable row")

        projected = _public_projection(record)
        projected["gen_ai.evidence.hash_prev"] = previous_public
        projected_hash = hashlib.sha256(canonical_json(projected)).hexdigest()
        projected["record_hash"] = projected_hash
        public_records.append(projected)
        trace_id = str(record.get("trace_id") or "")
        if trace_id in {original_trace, compensation_trace}:
            traces_seen.add(trace_id)
        mapping.append(
            {
                "projected_record_hash": projected_hash,
                "seq": int(row.get("seq") or 0),
                "source_record_hash": source_hash,
                "trace_id": trace_id,
            }
        )
        previous_source = source_hash
        previous_public = projected_hash
    if traces_seen != {original_trace, compensation_trace}:
        raise CollectionError("Gate6 source chain does not contain both linked traces")
    provenance = {
        "algorithm": "sha256",
        "excluded_field_classes": [
            "authorization credentials",
            "key material",
            "replayable approval credentials",
            "signatures over pre-projection records",
        ],
        "mapping": mapping,
        "projection": "public-field-projection/v1",
        "source": "PostgreSQL xa_gate6_events tenant chain prefix",
    }
    return public_records, provenance


def _validate_cross_system(
    effect: dict[str, Any],
    undo: dict[str, Any],
    business: dict[str, Any],
    events: list[dict[str, Any]],
    gate6: list[dict[str, Any]],
) -> None:
    effect_id = str(effect["effect_id"] or "")
    tenant_id = str(effect["tenant_id"] or "")
    if effect.get("status") != "compensated" or undo.get("status") != "completed":
        raise CollectionError("selected Effect and Undo request are not complete")
    if undo.get("effect_id") != effect_id or undo.get("tenant_id") != tenant_id:
        raise CollectionError("Undo request is not linked to the selected Effect")
    if business.get("create_effect_id") != effect_id or business.get("tenant_id") != tenant_id:
        raise CollectionError("business row is not linked to the selected Effect")
    if business.get("state") != "cancelled" or not business.get("cancelled_at"):
        raise CollectionError("reference business row is not in the compensated state")
    requester = str(effect.get("principal_sub") or "")
    if undo.get("requester_sub") != requester or not undo.get("approver_sub"):
        raise CollectionError("requester/approver identities are incomplete")
    if undo.get("approver_sub") == requester:
        raise CollectionError("separation of duty was not satisfied")
    required = {"effect_prepared", "undo_requested", "undo_approved", "compensated"}
    selected_events = [row for row in events if row.get("effect_id") == effect_id]
    event_types = {str(row.get("event_type") or "") for row in selected_events}
    if not required.issubset(event_types):
        raise CollectionError("Effect chain lacks required Identity + Undo events")
    event_by_type: dict[str, dict[str, Any]] = {}
    for event_type in required:
        matches = [row for row in selected_events if row.get("event_type") == event_type]
        if len(matches) != 1:
            raise CollectionError(f"Effect chain requires exactly one {event_type} event")
        event_by_type[event_type] = matches[0]
    request_id = str(undo.get("request_id") or "")
    original_trace = str(effect.get("trace_id") or "")
    compensation_trace = str(effect.get("compensation_trace_id") or "")
    if original_trace == compensation_trace:
        raise CollectionError("original and compensation traces must be distinct")
    if (
        event_by_type["effect_prepared"].get("actor_sub") != requester
        or event_by_type["effect_prepared"].get("payload", {}).get("trace_id") != original_trace
        or event_by_type["undo_requested"].get("actor_sub") != requester
        or event_by_type["undo_approved"].get("actor_sub") != undo.get("approver_sub")
        or event_by_type["compensated"].get("payload", {}).get("trace_id") != compensation_trace
    ):
        raise CollectionError("Effect event identities or traces do not match the selected workflow")
    linked_request_ids = {
        str(event_by_type[event_type].get("payload", {}).get("request_id") or "")
        for event_type in ("undo_requested", "undo_approved", "compensated")
    }
    if linked_request_ids != {request_id}:
        raise CollectionError("Effect events do not share the selected Undo request id")

    action_records = [row for row in gate6 if row.get("trace_id") == original_trace]
    compensation_records = [row for row in gate6 if row.get("trace_id") == compensation_trace]
    agent_id = str(effect.get("agent_id") or "")
    if not any(
        row.get("gen_ai.resilience.effect_id") == effect_id
        and row.get("gen_ai.governance.human_principal") == requester
        and row.get("gen_ai.governance.agent_id") == agent_id
        and row.get("gen_ai.governance.tenant_id") == tenant_id
        for row in action_records
    ):
        raise CollectionError("original Gate6 trace lacks the required identity/effect link")
    if not any(
        row.get("gen_ai.resilience.compensates_effect_id") == effect_id
        and row.get("gen_ai.governance.human_principal") == undo.get("approver_sub")
        and row.get("gen_ai.governance.tenant_id") == tenant_id
        for row in compensation_records
    ):
        raise CollectionError("public Gate6 projection lacks an original or compensation trace")


def _assignment(effect: dict[str, Any]) -> dict[str, Any]:
    snapshot = effect.get("authorization_snapshot")
    if not isinstance(snapshot, dict):
        raise CollectionError("Effect has no authorization assignment snapshot")
    assignment_id = str(snapshot.get("assignment_id") or "")
    try:
        version = int(snapshot.get("version"))
    except (TypeError, ValueError) as exc:
        raise CollectionError("authorization assignment version is absent") from exc
    if not assignment_id or version <= 0:
        raise CollectionError("authorization assignment identity is absent")
    subject_type = str(snapshot.get("subject_type") or "")
    subject_id = str(snapshot.get("subject_id") or "")
    snapshot_agent = str(snapshot.get("agent_id") or "")
    tools = sorted(str(item) for item in (snapshot.get("tools") or []))
    domains = sorted(str(item) for item in (snapshot.get("data_domains") or []))
    if subject_type not in {"human", "group"} or not subject_id:
        raise CollectionError("authorization assignment subject is incomplete")
    if snapshot_agent != str(effect["agent_id"]):
        raise CollectionError("authorization assignment Agent does not match the Effect")
    if str(effect["tool_name"]) not in tools or str(effect["data_domain"]) not in domains:
        raise CollectionError("authorization assignment does not cover the captured operation")
    return {
        "agent_id": str(effect["agent_id"]),
        "assignment": {
            "agent_id": snapshot_agent,
            "assignment_id": assignment_id,
            "data_domains": domains,
            "subject_id": subject_id,
            "subject_type": subject_type,
            "tools": tools,
            "version": version,
        },
        "principal_sub": str(effect["principal_sub"]),
        "tenant_id": str(effect["tenant_id"]),
    }


def _identity(effect: dict[str, Any], undo: dict[str, Any], assignment: dict[str, Any]) -> dict[str, Any]:
    return {
        "agent": {"id": str(effect["agent_id"])},
        "approver": {
            "sub": str(undo["approver_sub"]),
            "username": str(undo.get("approver_username") or ""),
        },
        "assignment": {
            "id": assignment["assignment"]["assignment_id"],
            "subject_id": assignment["assignment"]["subject_id"],
            "subject_type": assignment["assignment"]["subject_type"],
            "version": assignment["assignment"]["version"],
        },
        "claims_source": "persisted verified identity and authorization summaries",
        "requester": {
            "sub": str(effect["principal_sub"]),
            "username": str(effect.get("principal_username") or ""),
        },
        "schema": "xa-guard-public-identity-summary/v1",
        "tenant_id": str(effect["tenant_id"]),
    }


def _business_timeline(business: dict[str, Any]) -> dict[str, Any]:
    return {
        "after": {
            "observed_at": business["cancelled_at"],
            "state": "cancelled",
        },
        "before": {
            "basis": "reference create transition invariant and persisted created_at",
            "observed_at": business["created_at"],
            "state": "open",
        },
        "current": {
            "observed_from": "xa_reference_tickets",
            "state": business["state"],
        },
        "effect_id": business["create_effect_id"],
        "tenant_id": business["tenant_id"],
        "ticket_id": business["ticket_id"],
        "transition": "open_to_cancelled",
    }


def _iso8601(value: Any, label: str) -> str:
    try:
        parsed = datetime.fromisoformat(str(value).replace(" ", "T").replace("Z", "+00:00"))
    except ValueError as exc:
        raise CollectionError(f"{label} is not an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise CollectionError(f"{label} has no timezone")
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _git_source(run: CommandRunner) -> dict[str, Any]:
    revision = run(["git", "rev-parse", "HEAD"]).strip().lower()
    if not re.fullmatch(r"[0-9a-f]{7,64}", revision):
        raise CollectionError("git revision could not be determined")
    dirty = bool(run(["git", "status", "--porcelain", "--untracked-files=normal"]).strip())
    return {"dirty": dirty, "repository": ROOT.name, "revision": revision}


def _image_digest(reference: str, candidate: str, run: CommandRunner) -> str:
    match = _SHA256.fullmatch(candidate.lower())
    if match:
        return "sha256:" + match.group(1)
    repo_digests = run(["docker", "image", "inspect", reference, "--format", "{{json .RepoDigests}}"])
    try:
        parsed = json.loads(repo_digests)
    except json.JSONDecodeError:
        parsed = []
    if isinstance(parsed, list):
        for item in parsed:
            digest = str(item).rsplit("@", 1)[-1].lower()
            match = _SHA256.fullmatch(digest)
            if match:
                return "sha256:" + match.group(1)
    image_id = run(["docker", "image", "inspect", reference, "--format", "{{.Id}}"])
    match = _SHA256.fullmatch(image_id.strip().lower())
    if not match:
        raise CollectionError(f"image digest is unavailable for {reference}")
    return "sha256:" + match.group(1)


def _images(run: CommandRunner) -> list[dict[str, str]]:
    raw = run(["docker", "compose", "-f", str(COMPOSE), "images", "--format", "json"])
    try:
        parsed = json.loads(raw)
        rows = parsed if isinstance(parsed, list) else [parsed]
    except json.JSONDecodeError:
        try:
            rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
        except json.JSONDecodeError as exc:
            raise CollectionError("Compose image inventory is malformed") from exc
    discovered: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        repository = str(row.get("Repository") or row.get("Image") or "").strip()
        tag = str(row.get("Tag") or "").strip()
        reference = repository + (f":{tag}" if tag and tag != "<none>" else "")
        name = reference or str(row.get("Service") or row.get("ContainerName") or "").strip()
        if not reference:
            reference = name
        if not name or not reference:
            continue
        digest = _image_digest(reference, str(row.get("ID") or row.get("Digest") or ""), run)
        previous = discovered.setdefault(name, digest)
        if previous != digest:
            raise CollectionError(f"Compose image name maps to multiple digests: {name}")
    if not discovered:
        raise CollectionError("no running reference Compose images were discovered")
    return [{"digest": discovered[name], "name": name} for name in sorted(discovered)]


def _tools(run: CommandRunner) -> list[dict[str, str]]:
    docker_version = run(["docker", "version", "--format", "{{.Client.Version}}"]).strip()
    if not docker_version:
        raise CollectionError("Docker client version is unavailable")
    return sorted(
        [
            {"name": "docker", "version": docker_version},
            {"name": "python", "version": platform.python_version()},
            {"name": "xa-guard-evidence-collector", "version": "1"},
        ],
        key=lambda item: item["name"],
    )


def _prepare_output(output: Path) -> Path:
    if output.is_symlink():
        raise CollectionError("output directory must not be a symlink")
    if output.exists():
        if not output.is_dir():
            raise CollectionError("output path is not a directory")
        if any(output.iterdir()):
            raise CollectionError("output directory must be empty")
    else:
        output.mkdir(parents=True)
    return output.resolve(strict=True)


def _write_bytes(root: Path, relative: str, payload: bytes) -> None:
    normalized = normalize_artifact_path(relative)
    target = root.joinpath(*normalized.split("/"))
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        raise CollectionError(f"artifact output is a symlink: {relative}")
    target.write_bytes(payload)


def _write_json(root: Path, relative: str, value: Any) -> None:
    _write_bytes(root, relative, canonical_json(value) + b"\n")


def _write_jsonl(root: Path, relative: str, records: Iterable[dict[str, Any]]) -> None:
    payload = b"".join(canonical_json(record) + b"\n" for record in records)
    if not payload:
        raise CollectionError(f"chain artifact is empty: {relative}")
    _write_bytes(root, relative, payload)


def _copy_acceptance_reports(root: Path, reports: Iterable[str | Path]) -> list[dict[str, Any]]:
    copied: list[dict[str, Any]] = []
    destinations: set[str] = set()
    for source_value in reports:
        source = Path(source_value)
        if source.is_symlink():
            raise CollectionError("acceptance report must not be a symlink")
        try:
            source = source.resolve(strict=True)
        except FileNotFoundError as exc:
            raise CollectionError("acceptance report does not exist") from exc
        if not source.is_file():
            raise CollectionError("acceptance report is not a regular file")
        relative = normalize_artifact_path(f"acceptance/{source.name}")
        if relative in destinations:
            raise CollectionError("acceptance report names must be unique")
        payload = source.read_bytes()
        findings = scan_secret_bytes(relative, payload)
        if findings:
            raise CollectionError("acceptance report contains material forbidden from evidence")
        _write_bytes(root, relative, payload)
        destinations.add(relative)
        copied.append(
            {
                "bytes": len(payload),
                "path": relative,
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    return sorted(copied, key=lambda item: item["path"])


def collect_bundle(
    output: str | Path,
    *,
    effect_id: str = "",
    acceptance_reports: Iterable[str | Path] = (),
    query_sql: SqlQuery | None = None,
    command_runner: CommandRunner | None = None,
) -> dict[str, Any]:
    """Collect and independently validate one compensated reference workflow."""

    query_sql = query_sql or _reference_sql
    command_runner = command_runner or _run_command

    # Capture source/runtime provenance before creating an untracked output tree.
    source = _git_source(command_runner)
    images = _images(command_runner)
    tools = _tools(command_runner)

    effect = _select_effect(effect_id, query_sql)
    selected_effect = _safe_identifier(str(effect.get("effect_id") or ""), "effect id")
    tenant_id = _safe_identifier(str(effect.get("tenant_id") or ""), "tenant id")
    original_trace = _safe_identifier(str(effect.get("trace_id") or ""), "original trace id")
    compensation_trace = _safe_identifier(
        str(effect.get("compensation_trace_id") or ""), "compensation trace id"
    )
    agent_id = _safe_identifier(str(effect.get("agent_id") or ""), "agent id")
    undo = _select_undo(selected_effect, tenant_id, query_sql)
    business_row = _select_business(selected_effect, tenant_id, query_sql)
    effect_events = _select_effect_events(selected_effect, tenant_id, query_sql)
    gate6_rows = _select_gate6_rows(tenant_id, original_trace, compensation_trace, query_sql)
    gate6_records, gate6_provenance = _gate6_projection(gate6_rows, original_trace, compensation_trace)
    _validate_cross_system(effect, undo, business_row, effect_events, gate6_records)
    assignment = _assignment(effect)
    identity = _identity(effect, undo, assignment)
    business = _business_timeline(business_row)

    root = _prepare_output(Path(output))
    _write_json(root, "assignment.json", assignment)
    _write_json(root, "business.json", business)
    _write_json(
        root, "effect.json", {key: effect[key] for key in _EFFECT_FIELDS if key != "authorization_snapshot"}
    )
    _write_json(root, "identity.json", identity)
    _write_json(root, "undo-request.json", undo)
    _write_jsonl(root, "effect-events.jsonl", effect_events)
    _write_jsonl(root, "gate6.jsonl", gate6_records)
    _write_json(root, "gate6-source-provenance.json", gate6_provenance)
    copied_reports = _copy_acceptance_reports(root, acceptance_reports)
    _write_json(root, "acceptance/index.json", {"reports": copied_reports})

    assignment_hash = hashlib.sha256((root / "assignment.json").read_bytes()).hexdigest()
    provenance = {
        "acceptance_reports": copied_reports,
        "artifact_sources": [
            {
                "artifacts": ["effect-events.jsonl", "effect.json"],
                "source": "xa_effects and xa_effect_events",
            },
            {"artifacts": ["gate6-source-provenance.json", "gate6.jsonl"], "source": "xa_gate6_events"},
            {"artifacts": ["undo-request.json"], "source": "xa_undo_requests"},
            {"artifacts": ["business.json"], "source": "xa_reference_tickets"},
        ],
        "collection_transport": "docker compose exec psql through the reference acceptance helper",
        "database_connection_material_captured": False,
        "effect_id": selected_effect,
        "images": images,
        "source": source,
        "tools": tools,
    }
    _write_json(root, "artifact-source-provenance.json", provenance)

    completed_event = next(
        row
        for row in effect_events
        if row.get("effect_id") == selected_effect and row.get("event_type") == "compensated"
    )
    metadata = {
        "acceptance": {
            "assertions": sorted(
                [
                    {
                        "evidence": ["assignment.json", "identity.json", "undo-request.json"],
                        "id": "identity-separated",
                        "passed": True,
                        "statement": "Requester and approver are distinct persisted subjects under the captured assignment.",
                    },
                    {
                        "evidence": ["effect-events.jsonl", "effect.json", "undo-request.json"],
                        "id": "undo-compensated",
                        "passed": True,
                        "statement": "The approved Undo request reached the compensated Effect state.",
                    },
                    {
                        "evidence": ["business.json", "effect-events.jsonl"],
                        "id": "business-restored",
                        "passed": True,
                        "statement": "The reference ticket transitioned from open to cancelled under compensation.",
                    },
                    {
                        "evidence": [
                            "effect-events.jsonl",
                            "gate6-source-provenance.json",
                            "gate6.jsonl",
                        ],
                        "id": "traces-cross-linked",
                        "passed": True,
                        "statement": "Original and compensation traces are linked across the Effect and Gate6 chains.",
                    },
                ],
                key=lambda item: item["id"],
            ),
            "boundaries": sorted(
                [
                    {
                        "id": "business-before-state",
                        "statement": "The open before-state is reconstructed from the reference create invariant and persisted transition timestamps, not a separate point-in-time snapshot.",
                    },
                    {
                        "id": "delivery-scope",
                        "statement": "This bundle proves one reference Compose workflow and does not by itself establish HA readiness.",
                    },
                    {
                        "id": "execution-semantics",
                        "statement": "Compensation uses at-least-once execution with downstream idempotency, not absolute exactly-once delivery.",
                    },
                    {
                        "id": "gate6-public-projection",
                        "statement": "Gate6 evidence is a chain-verified public projection; replayable credentials are excluded and source hashes are mapped separately.",
                    },
                ],
                key=lambda item: item["id"],
            ),
        },
        "chains": {
            "effect": {"algorithm": "sha256", "path": "effect-events.jsonl"},
            "gate6": {"algorithm": "sha256", "path": "gate6.jsonl"},
        },
        "cross_links": {
            "agent_id": agent_id,
            "approver_sub": str(undo["approver_sub"]),
            "assignment_artifact": "assignment.json",
            "assignment_id": assignment["assignment"]["assignment_id"],
            "assignment_snapshot_sha256": assignment_hash,
            "assignment_version": assignment["assignment"]["version"],
            "business_artifact": "business.json",
            "business_effect_id": selected_effect,
            "compensation_trace_id": compensation_trace,
            "effect_id": selected_effect,
            "original_trace_id": original_trace,
            "requester_sub": str(effect["principal_sub"]),
            "tenant_id": tenant_id,
        },
        "images": images,
        "run": {
            "completed_at": _iso8601(completed_event["occurred_at"], "completion time"),
            "id": f"reference-identity-undo-{selected_effect}",
            "mode": "docker-compose-reference",
            "started_at": _iso8601(effect["prepared_at"], "start time"),
        },
        "source": source,
        "tools": tools,
    }
    _write_json(root, "sealing-metadata.json", metadata)

    try:
        verify_effect_chain(root / "effect-events.jsonl", "sha256")
        verify_gate6_chain(root / "gate6.jsonl", "sha256")
        paths = enumerate_bundle_files(root)
        scan_bundle_for_secrets(root, paths)
    except EvidenceError as exc:
        raise CollectionError(f"staging evidence validation failed: {exc}") from exc
    return {
        "artifact_count": len(paths),
        "bundle": str(root),
        "effect_id": selected_effect,
        "metadata": str(root / "sealing-metadata.json"),
        "ok": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect XA-Guard Identity + Undo evidence")
    parser.add_argument("--output", required=True, help="new or empty staging directory")
    parser.add_argument("--effect-id", default="", help="compensated Effect; latest when omitted")
    parser.add_argument(
        "--acceptance-report",
        action="append",
        default=[],
        help="optional safe acceptance report to copy (repeatable)",
    )
    args = parser.parse_args(argv)
    try:
        result = collect_bundle(
            args.output,
            effect_id=args.effect_id,
            acceptance_reports=args.acceptance_report,
        )
    except (CollectionError, OSError, subprocess.SubprocessError) as exc:
        print(
            json.dumps({"error": str(exc), "ok": False}, ensure_ascii=False, sort_keys=True), file=sys.stderr
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
