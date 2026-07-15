from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from scripts.seal_identity_undo_evidence import seal_bundle
from scripts.verify_identity_undo_evidence import (
    DEFAULT_SCHEMA,
    EvidenceError,
    canonical_json,
    normalize_artifact_path,
    scan_secret_bytes,
    unsigned_manifest_bytes,
    validate_manifest_shape,
    verify_bundle,
)
from xa_guard.audit.sm_crypto import generate_sm2_keypair, write_sm2_keyfile

TENANT = "tenant-a"
AGENT = "general-office-agent"
EFFECT = "eff-0001"
ACTION_TRACE = "trace-original-0001"
COMPENSATION_TRACE = "trace-compensation-0001"
REQUESTER = "alice-id"
APPROVER = "dora-id"
ASSIGNMENT = "asg-0001"


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _gate6_record(previous: str, **values: Any) -> dict[str, Any]:
    record = {"gen_ai.evidence.hash_prev": previous, **values}
    record["record_hash"] = hashlib.sha256(canonical_json(record)).hexdigest()
    return record


def _effect_event(sequence: int, previous: str, event_type: str, actor: str, payload: dict[str, Any]) -> dict[str, Any]:
    hashed = {
        "tenant_id": TENANT,
        "effect_id": EFFECT,
        "event_type": event_type,
        "actor_sub": actor,
        "payload": payload,
        "prev_hash": previous,
    }
    return {"seq": sequence, **hashed, "record_hash": hashlib.sha256(canonical_json(hashed)).hexdigest()}


def _write_chains(bundle: Path) -> None:
    action = _gate6_record(
        "",
        trace_id=ACTION_TRACE,
        **{
            "gen_ai.governance.tenant_id": TENANT,
            "gen_ai.governance.human_principal": REQUESTER,
            "gen_ai.governance.agent_id": AGENT,
            "gen_ai.resilience.effect_id": EFFECT,
            "gen_ai.resilience.compensates_effect_id": "",
        },
    )
    compensation = _gate6_record(
        action["record_hash"],
        trace_id=COMPENSATION_TRACE,
        **{
            "gen_ai.governance.tenant_id": TENANT,
            "gen_ai.governance.human_principal": APPROVER,
            "gen_ai.governance.agent_id": AGENT,
            "gen_ai.resilience.effect_id": "",
            "gen_ai.resilience.compensates_effect_id": EFFECT,
        },
    )
    (bundle / "gate6.jsonl").write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in (action, compensation)),
        encoding="utf-8",
    )

    events: list[dict[str, Any]] = []
    previous = ""
    for sequence, event_type, actor, payload in (
        (1, "effect_prepared", REQUESTER, {"trace_id": ACTION_TRACE}),
        (2, "undo_requested", REQUESTER, {"request_id": "undo-0001"}),
        (3, "undo_approved", APPROVER, {"request_id": "undo-0001"}),
        (4, "compensated", "worker-1", {"request_id": "undo-0001", "trace_id": COMPENSATION_TRACE}),
    ):
        event = _effect_event(sequence, previous, event_type, actor, payload)
        events.append(event)
        previous = event["record_hash"]
    (bundle / "effect-events.jsonl").write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in events), encoding="utf-8"
    )


def _metadata(bundle: Path) -> dict[str, Any]:
    assignment_hash = hashlib.sha256((bundle / "assignment.json").read_bytes()).hexdigest()
    return {
        "run": {
            "id": "reference-e2e-20260713",
            "mode": "docker-compose-reference",
            "started_at": "2026-07-13T00:00:00Z",
            "completed_at": "2026-07-13T00:02:00Z",
        },
        "source": {"repository": "XA-Guard", "revision": "0123456789abcdef", "dirty": True},
        "images": [
            {"name": "xa-guard", "digest": "sha256:" + "b" * 64},
            {"name": "postgres", "digest": "sha256:" + "a" * 64},
        ],
        "tools": [
            {"name": "pytest", "version": "8.4.1"},
            {"name": "docker", "version": "29.5.2"},
        ],
        "chains": {
            "gate6": {"path": "gate6.jsonl", "algorithm": "sha256"},
            "effect": {"path": "effect-events.jsonl", "algorithm": "sha256"},
        },
        "cross_links": {
            "tenant_id": TENANT,
            "agent_id": AGENT,
            "effect_id": EFFECT,
            "original_trace_id": ACTION_TRACE,
            "compensation_trace_id": COMPENSATION_TRACE,
            "requester_sub": REQUESTER,
            "approver_sub": APPROVER,
            "business_effect_id": EFFECT,
            "business_artifact": "business.json",
            "assignment_artifact": "assignment.json",
            "assignment_snapshot_sha256": assignment_hash,
            "assignment_id": ASSIGNMENT,
            "assignment_version": 3,
        },
        "acceptance": {
            "assertions": [
                {
                    "id": "undo-restored",
                    "statement": "Approved compensation restored the ticket state.",
                    "passed": True,
                    "evidence": ["gate6.jsonl", "business.json", "effect-events.jsonl"],
                },
                {
                    "id": "identity-separated",
                    "statement": "Requester and approver are distinct verified subjects.",
                    "passed": True,
                    "evidence": ["assignment.json", "effect-events.jsonl"],
                },
            ],
            "boundaries": [
                {
                    "id": "delivery-scope",
                    "statement": "This bundle proves the reference Compose run, not HA readiness.",
                },
                {
                    "id": "execution-semantics",
                    "statement": "Compensation is at-least-once with downstream idempotency.",
                },
            ],
        },
    }


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    _write_json(bundle / "business.json", {"ticket": {"effect_id": EFFECT, "status": "cancelled"}})
    _write_json(
        bundle / "assignment.json",
        {
            "tenant_id": TENANT,
            "principal_sub": REQUESTER,
            "agent_id": AGENT,
            "assignment": {"assignment_id": ASSIGNMENT, "version": 3},
        },
    )
    _write_chains(bundle)
    metadata = tmp_path / "metadata.json"
    _write_json(metadata, _metadata(bundle))
    private_key = tmp_path / "seal-private.key"
    private_hex, public_hex = generate_sm2_keypair()
    write_sm2_keyfile(private_key, private_hex, public_hex)
    return bundle, metadata, private_key


def test_seal_and_independently_verify_strict_sm2_bundle(tmp_path: Path) -> None:
    bundle, metadata, private_key = _fixture(tmp_path)

    result = seal_bundle(bundle, metadata, private_key)
    manifest = json.loads((bundle / "artifact-manifest.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert result["signature_algorithm"] == "SM2-with-SM3"
    assert [item["path"] for item in manifest["artifacts"]] == sorted(
        item["path"] for item in manifest["artifacts"]
    )
    assert [item["name"] for item in manifest["images"]] == ["postgres", "xa-guard"]
    assert [item["name"] for item in manifest["tools"]] == ["docker", "pytest"]
    assert "private" not in json.dumps(manifest).lower()
    assert len(manifest["signature"]["public_key"]) == 128
    assert verify_bundle(bundle)["artifact_count"] == 4
    assert verify_bundle(bundle, expected_key_id=manifest["signature"]["key_id"])["ok"] is True
    with pytest.raises(EvidenceError, match="pinned key id"):
        verify_bundle(bundle, expected_key_id="0" * 16)

    first_unsigned = unsigned_manifest_bytes(manifest)
    seal_bundle(bundle, metadata, private_key)
    second = json.loads((bundle / "artifact-manifest.json").read_text(encoding="utf-8"))
    assert unsigned_manifest_bytes(second) == first_unsigned


def test_verifier_rejects_tampered_artifact_bytes(tmp_path: Path) -> None:
    bundle, metadata, private_key = _fixture(tmp_path)
    seal_bundle(bundle, metadata, private_key)
    (bundle / "business.json").write_text('{"effect_id":"different"}\n', encoding="utf-8")

    with pytest.raises(EvidenceError, match="SHA-256 mismatch|byte length mismatch"):
        verify_bundle(bundle)


def test_manifest_signature_binds_public_metadata(tmp_path: Path) -> None:
    bundle, metadata, private_key = _fixture(tmp_path)
    seal_bundle(bundle, metadata, private_key)
    path = bundle / "artifact-manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["source"]["revision"] = "tampered-revision"
    _write_json(path, manifest)

    with pytest.raises(EvidenceError, match="signature is invalid"):
        verify_bundle(bundle)


def test_sealer_independently_rejects_corrupt_effect_chain(tmp_path: Path) -> None:
    bundle, metadata, private_key = _fixture(tmp_path)
    path = bundle / "effect-events.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[-1])
    record["payload"]["trace_id"] = "tampered"
    lines[-1] = json.dumps(record, sort_keys=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(EvidenceError, match="Effect event hash mismatch"):
        seal_bundle(bundle, metadata, private_key)


@pytest.mark.parametrize(
    "name,payload",
    [
        ("jwt.txt", b"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhbGljZSJ9.abcdefghijklmnop"),
        ("password.json", b'{"password":"not-redacted"}'),
        ("environment.json", b'{"POSTGRES_PASSWORD":"not-redacted"}'),
        ("client.json", b'{"client_secret":"not-redacted"}'),
        ("kek.json", b'{"kek":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="}'),
        ("kek.env", b"XA_GUARD_KEK_KEYRING=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="),
        ("dsn.txt", b"postgresql://db-user:db-pass@postgres/control"),
        ("command.txt", b"tool --password not-redacted"),
        ("recovery.json", b'{"recovery":{"ticket_id":"T-1"}}'),
        ("private.key", b"private: " + b"1" * 64),
    ],
)
def test_secret_scanner_blocks_sensitive_material(name: str, payload: bytes) -> None:
    assert scan_secret_bytes(name, payload)


def test_secret_scanner_allows_redactions_hashes_and_public_material() -> None:
    safe = {
        "password": "[redacted]",
        "client_secret": "<redacted>",
        "dsn_sha256": "a" * 64,
        "recovery_ciphertext": "opaque-ciphertext",
        "kek_key_id": "reference-v2",
        "public_key": "b" * 128,
    }
    assert scan_secret_bytes("safe.json", canonical_json(safe)) == []
    assert scan_secret_bytes("commands.txt", b"tool --password $POSTGRES_PASSWORD") == []
    assert scan_secret_bytes("boundaries.txt", b"The client secret is excluded from evidence.") == []


def test_sealer_scans_public_manifest_metadata_for_secrets(tmp_path: Path) -> None:
    bundle, metadata, private_key = _fixture(tmp_path)
    value = json.loads(metadata.read_text(encoding="utf-8"))
    value["source"]["repository"] = "postgresql://user:pass@db/control"
    _write_json(metadata, value)

    with pytest.raises(EvidenceError, match="metadata secret scan"):
        seal_bundle(bundle, metadata, private_key)


@pytest.mark.parametrize(
    "path",
    ["../escape.json", "/absolute.json", "C:/escape.json", "a\\b.json", "./a", "safe.txt:stream", "CON"],
)
def test_path_normalization_rejects_traversal_and_aliases(path: str) -> None:
    with pytest.raises(EvidenceError):
        normalize_artifact_path(path)


def test_sealer_rejects_symlinked_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bundle, metadata, private_key = _fixture(tmp_path)
    target = tmp_path / "outside.txt"
    target.write_text("outside", encoding="utf-8")
    try:
        (bundle / "linked.txt").symlink_to(target)
    except OSError:
        linked = bundle / "linked.txt"
        linked.write_text("simulated link", encoding="utf-8")
        original = Path.is_symlink
        monkeypatch.setattr(Path, "is_symlink", lambda path: path.name == "linked.txt" or original(path))

    with pytest.raises(EvidenceError, match="symlink"):
        seal_bundle(bundle, metadata, private_key)


def test_sealer_rejects_private_key_inside_bundle(tmp_path: Path) -> None:
    bundle, metadata, private_key = _fixture(tmp_path)
    inside = bundle / "private.key"
    inside.write_bytes(private_key.read_bytes())

    with pytest.raises(EvidenceError, match="outside"):
        seal_bundle(bundle, metadata, inside)


def test_cross_links_fail_closed_on_self_approval(tmp_path: Path) -> None:
    bundle, metadata, private_key = _fixture(tmp_path)
    value = json.loads(metadata.read_text(encoding="utf-8"))
    value["cross_links"]["approver_sub"] = REQUESTER
    _write_json(metadata, value)

    with pytest.raises(EvidenceError, match="distinct subjects"):
        seal_bundle(bundle, metadata, private_key)


def test_sealer_refuses_failed_acceptance_assertion(tmp_path: Path) -> None:
    bundle, metadata, private_key = _fixture(tmp_path)
    value = json.loads(metadata.read_text(encoding="utf-8"))
    value["acceptance"]["assertions"][0]["passed"] = False
    _write_json(metadata, value)

    with pytest.raises(EvidenceError, match="not all passing"):
        seal_bundle(bundle, metadata, private_key)


def test_no_hmac_fallback_for_invalid_sm2_private_key(tmp_path: Path) -> None:
    bundle, metadata, _ = _fixture(tmp_path)
    invalid = tmp_path / "invalid.key"
    invalid.write_text("demo-hmac-key", encoding="utf-8")

    with pytest.raises(EvidenceError, match="strict SM2-with-SM3 signing failed"):
        seal_bundle(bundle, metadata, invalid)


def test_manifest_shape_rejects_non_sm2_algorithm(tmp_path: Path) -> None:
    bundle, metadata, private_key = _fixture(tmp_path)
    seal_bundle(bundle, metadata, private_key)
    manifest = json.loads((bundle / "artifact-manifest.json").read_text(encoding="utf-8"))
    manifest["signature"]["algorithm"] = "HMAC-SHA256"

    with pytest.raises(EvidenceError, match="only strict SM2"):
        validate_manifest_shape(manifest)


def test_checked_in_schema_is_valid_json() -> None:
    schema = json.loads(DEFAULT_SCHEMA.read_text(encoding="utf-8"))
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["properties"]["schema"]["const"] == "xa-guard-evidence/v1"
