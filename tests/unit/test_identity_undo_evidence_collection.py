from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from scripts.collect_identity_undo_evidence import CollectionError, collect_bundle
from scripts.seal_identity_undo_evidence import seal_bundle
from scripts.verify_identity_undo_evidence import canonical_json, scan_bundle_for_secrets
from xa_guard.audit.sm_crypto import generate_sm2_keypair, write_sm2_keyfile


TENANT = "acme"
EFFECT = "eff-0123456789abcdef0123456789abcdef"
REQUEST = "undo-0123456789abcdef0123456789abcdef"
ACTION_TRACE = "11111111-1111-4111-8111-111111111111"
COMPENSATION_TRACE = "22222222-2222-4222-8222-222222222222"
REQUESTER = "alice-sub"
APPROVER = "dora-sub"
AGENT = "general-office-agent"
IMAGE_ID = "sha256:" + "a" * 64


def _effect_event(
    sequence: int,
    previous: str,
    event_type: str,
    actor: str,
    payload: dict[str, Any],
    occurred_at: str,
) -> dict[str, Any]:
    hashed = {
        "tenant_id": TENANT,
        "effect_id": EFFECT,
        "event_type": event_type,
        "actor_sub": actor,
        "payload": payload,
        "prev_hash": previous,
    }
    return {
        "seq": sequence,
        **hashed,
        "occurred_at": occurred_at,
        "record_hash": hashlib.sha256(canonical_json(hashed)).hexdigest(),
    }


def _effect_events() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    previous = ""
    values = (
        ("effect_prepared", REQUESTER, {"trace_id": ACTION_TRACE}, "2026-07-13T00:00:00+00:00"),
        ("effect_available", REQUESTER, {"result_sha256": "b" * 64}, "2026-07-13T00:00:01+00:00"),
        ("undo_requested", REQUESTER, {"request_id": REQUEST}, "2026-07-13T00:00:02+00:00"),
        ("undo_approved", APPROVER, {"request_id": REQUEST}, "2026-07-13T00:00:03+00:00"),
        (
            "compensation_started",
            "worker-1",
            {"lease_seconds": 60, "request_id": REQUEST},
            "2026-07-13T00:00:04+00:00",
        ),
        (
            "compensated",
            "worker-1",
            {"request_id": REQUEST, "trace_id": COMPENSATION_TRACE},
            "2026-07-13T00:00:05+00:00",
        ),
    )
    for sequence, (event_type, actor, payload, occurred_at) in enumerate(values, 1):
        row = _effect_event(sequence, previous, event_type, actor, payload, occurred_at)
        rows.append(row)
        previous = row["record_hash"]
    return rows


def _gate_record(previous: str, **values: Any) -> dict[str, Any]:
    record = {
        "gen_ai.evidence.hash_prev": previous,
        "gen_ai.tool.approval_token": "credential-must-not-leave-the-database",
        "gen_ai.governance.capability_token": {"client_secret": "also-not-public"},
        "gen_ai.tool.parameters": {"password": "not-public", "safe": "value"},
        **values,
    }
    record["record_hash"] = hashlib.sha256(canonical_json(record)).hexdigest()
    return record


def _gate_rows() -> list[dict[str, Any]]:
    first = _gate_record(
        "",
        trace_id="00000000-0000-4000-8000-000000000000",
        **{"gen_ai.governance.tenant_id": TENANT},
    )
    action = _gate_record(
        first["record_hash"],
        trace_id=ACTION_TRACE,
        **{
            "gen_ai.governance.tenant_id": TENANT,
            "gen_ai.governance.human_principal": REQUESTER,
            "gen_ai.governance.agent_id": AGENT,
            "gen_ai.identity.verified": True,
            "gen_ai.resilience.effect_id": EFFECT,
            "gen_ai.resilience.compensates_effect_id": "",
        },
    )
    compensation = _gate_record(
        action["record_hash"],
        trace_id=COMPENSATION_TRACE,
        **{
            "gen_ai.governance.tenant_id": TENANT,
            "gen_ai.governance.human_principal": APPROVER,
            "gen_ai.governance.agent_id": AGENT,
            "gen_ai.identity.verified": True,
            "gen_ai.resilience.effect_id": "",
            "gen_ai.resilience.compensates_effect_id": EFFECT,
        },
    )
    rows = []
    for sequence, record in enumerate((first, action, compensation), 1):
        rows.append(
            {
                "seq": sequence,
                "tenant_id": TENANT,
                "trace_id": record["trace_id"],
                "record": record,
                "prev_hash": record["gen_ai.evidence.hash_prev"],
                "record_hash": record["record_hash"],
                "source_instance": "xa-guard-1",
                "occurred_at": f"2026-07-13T00:00:0{sequence}+00:00",
            }
        )
    return rows


def _effect() -> dict[str, Any]:
    return {
        "effect_id": EFFECT,
        "tenant_id": TENANT,
        "trace_id": ACTION_TRACE,
        "principal_sub": REQUESTER,
        "principal_username": "alice",
        "agent_id": AGENT,
        "data_domain": "engineering_docs",
        "tool_name": "business_submit_ticket",
        "args_sha256": "1" * 64,
        "contract_version": "2",
        "contract_hash": "2" * 64,
        "side_effect_level": "write",
        "reversibility": "compensatable",
        "status": "compensated",
        "prepared_at": "2026-07-13T00:00:00+00:00",
        "completed_at": "2026-07-13T00:00:01+00:00",
        "undo_expires_at": "2026-07-13T01:00:00+00:00",
        "result_sha256": "3" * 64,
        "downstream_reference": "TKT-001",
        "compensation_trace_id": COMPENSATION_TRACE,
        "retry_count": 0,
        "last_error_code": "",
        "authorization_snapshot": {
            "assignment_id": "asg-reference-engineering",
            "version": 3,
            "subject_type": "group",
            "subject_id": "engineering",
            "agent_id": AGENT,
            "tools": ["business_submit_ticket"],
            "data_domains": ["engineering_docs"],
        },
        # A future adapter returning SELECT * must still not leak these extras.
        "wrapped_dek": "not-public",
        "recovery_ciphertext": "not-public",
        "database_url": "postgresql://user:pass@example.invalid/db",
    }


def _undo() -> dict[str, Any]:
    return {
        "request_id": REQUEST,
        "effect_id": EFFECT,
        "tenant_id": TENANT,
        "idempotency_sha256": "4" * 64,
        "requester_sub": REQUESTER,
        "requester_username": "alice",
        "reason_sha256": "5" * 64,
        "status": "completed",
        "approver_sub": APPROVER,
        "approver_username": "dora",
        "decision_reason_sha256": "6" * 64,
        "compensation_args_sha256": "7" * 64,
        "requested_at": "2026-07-13T00:00:02+00:00",
        "decided_at": "2026-07-13T00:00:03+00:00",
        "internal_authorization": "not-public",
    }


def _business() -> dict[str, Any]:
    return {
        "ticket_id": "TKT-001",
        "tenant_id": TENANT,
        "state": "cancelled",
        "create_effect_id": EFFECT,
        "correlation_id": ACTION_TRACE,
        "created_at": "2026-07-13T00:00:01+00:00",
        "cancelled_at": "2026-07-13T00:00:05+00:00",
        "title": "password=not-public",
    }


class FakeRuntime:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.commands: list[list[str]] = []

    def sql(self, query: str) -> str:
        self.queries.append(query)
        values: dict[str, Any] = {
            "evidence:effect */": _effect(),
            "evidence:undo */": _undo(),
            "evidence:business */": _business(),
            "evidence:effect-events */": _effect_events(),
            "evidence:gate6 */": _gate_rows(),
        }
        for marker, value in values.items():
            if marker in query:
                return json.dumps(value, sort_keys=True)
        raise AssertionError(f"unexpected SQL: {query}")

    def command(self, args: list[str]) -> str:
        self.commands.append(args)
        if args == ["git", "rev-parse", "HEAD"]:
            return "0123456789abcdef0123456789abcdef01234567"
        if args[:2] == ["git", "status"]:
            return ""
        if args[:2] == ["docker", "compose"]:
            return json.dumps(
                [
                    {
                        "Repository": "xa-guard/reference",
                        "Tag": "0.2.0",
                        "ID": IMAGE_ID,
                    },
                    {
                        "Repository": "postgres",
                        "Tag": "17.6",
                        "ID": "sha256:" + "b" * 64,
                    },
                ]
            )
        if args == ["docker", "version", "--format", "{{.Client.Version}}"]:
            return "29.5.2"
        raise AssertionError(f"unexpected subprocess: {args}")


def _files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_collection_is_deterministic_secret_free_and_sealable(tmp_path: Path) -> None:
    report = tmp_path / "fault-report.json"
    report.write_text('{"ok":true,"suite":"fault-injection"}\n', encoding="utf-8")
    first_runtime = FakeRuntime()
    second_runtime = FakeRuntime()
    first = tmp_path / "first"
    second = tmp_path / "second"

    result = collect_bundle(
        first,
        effect_id=EFFECT,
        acceptance_reports=[report],
        query_sql=first_runtime.sql,
        command_runner=first_runtime.command,
    )
    collect_bundle(
        second,
        effect_id=EFFECT,
        acceptance_reports=[report],
        query_sql=second_runtime.sql,
        command_runner=second_runtime.command,
    )

    assert result["ok"] is True
    assert _files(first) == _files(second)
    assert any("status='compensated'" in query and EFFECT in query for query in first_runtime.queries)
    assert any(command[:2] == ["docker", "compose"] for command in first_runtime.commands)
    scan_bundle_for_secrets(first, _files(first))
    all_bytes = b"".join(_files(first).values())
    for forbidden in (
        b"credential-must-not-leave-the-database",
        b"also-not-public",
        b"postgresql://",
        b"internal_authorization",
        b"recovery_ciphertext",
        b"wrapped_dek",
        b"password=not-public",
    ):
        assert forbidden not in all_bytes

    metadata = json.loads((first / "sealing-metadata.json").read_text(encoding="utf-8"))
    assignment = json.loads((first / "assignment.json").read_text(encoding="utf-8"))
    business = json.loads((first / "business.json").read_text(encoding="utf-8"))
    gate6 = [json.loads(line) for line in (first / "gate6.jsonl").read_text().splitlines()]
    provenance = json.loads((first / "gate6-source-provenance.json").read_text(encoding="utf-8"))
    assert metadata["cross_links"]["assignment_id"] == "asg-reference-engineering"
    assert assignment["assignment"]["version"] == 3
    assert business["before"]["state"] == "open"
    assert business["current"]["state"] == "cancelled"
    assert {row["trace_id"] for row in gate6} >= {ACTION_TRACE, COMPENSATION_TRACE}
    assert len(provenance["mapping"]) == len(gate6)
    assert provenance["mapping"][-1]["source_record_hash"] != gate6[-1]["record_hash"]

    private_key = tmp_path / "seal-private.key"
    private_hex, public_hex = generate_sm2_keypair()
    write_sm2_keyfile(private_key, private_hex, public_hex)
    sealed = seal_bundle(first, first / "sealing-metadata.json", private_key)
    assert sealed["ok"] is True


def test_collection_uses_latest_compensated_effect_when_id_is_omitted(tmp_path: Path) -> None:
    runtime = FakeRuntime()

    result = collect_bundle(tmp_path / "bundle", query_sql=runtime.sql, command_runner=runtime.command)

    effect_query = next(query for query in runtime.queries if "evidence:effect */" in query)
    assert "status='compensated'" in effect_query
    assert "effect_id=" not in effect_query
    assert result["effect_id"] == EFFECT


def test_collection_rejects_unsafe_effect_id_before_database_query(tmp_path: Path) -> None:
    runtime = FakeRuntime()

    with pytest.raises(CollectionError, match="unsafe format"):
        collect_bundle(
            tmp_path / "bundle",
            effect_id="eff-x' OR true --",
            query_sql=runtime.sql,
            command_runner=runtime.command,
        )

    assert runtime.queries == []


def test_collection_refuses_nonempty_or_symlink_output(tmp_path: Path) -> None:
    runtime = FakeRuntime()
    nonempty = tmp_path / "nonempty"
    nonempty.mkdir()
    (nonempty / "stale.json").write_text("{}", encoding="utf-8")
    with pytest.raises(CollectionError, match="must be empty"):
        collect_bundle(nonempty, query_sql=runtime.sql, command_runner=runtime.command)

    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable")
    with pytest.raises(CollectionError, match="symlink"):
        collect_bundle(link, query_sql=runtime.sql, command_runner=runtime.command)
