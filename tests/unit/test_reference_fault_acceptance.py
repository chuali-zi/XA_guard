from __future__ import annotations

import base64
import json

from scripts.verify_reference_faults import (
    SCHEMA,
    build_fault_evidence,
    mutate_jwt_claim,
    mutate_jwt_signature,
    sanitize_evidence,
    status_matches,
    validate_retry_schedule,
)


def _jwt(payload: dict[str, object]) -> str:
    def encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode().rstrip("=")

    return ".".join(
        (
            encode(b'{"alg":"RS256","kid":"reference"}'),
            encode(json.dumps(payload, separators=(",", ":")).encode()),
            encode(b"not-a-real-signature-but-long-enough"),
        )
    )


def _payload(token: str) -> dict[str, object]:
    raw = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))


def test_jwt_claim_mutation_changes_only_payload_and_does_not_resign() -> None:
    token = _jwt({"sub": "alice", "tenant_id": "acme-corp", "azp": "general-office-agent"})

    forged = mutate_jwt_claim(token, "tenant_id", "beta-corp")

    assert forged.split(".")[0] == token.split(".")[0]
    assert forged.split(".")[2] == token.split(".")[2]
    assert _payload(forged)["tenant_id"] == "beta-corp"
    assert _payload(forged)["sub"] == "alice"


def test_jwt_signature_mutation_preserves_header_and_payload() -> None:
    token = _jwt({"sub": "alice"})

    corrupted = mutate_jwt_signature(token)

    assert corrupted != token
    assert corrupted.split(".")[:2] == token.split(".")[:2]
    assert len(corrupted.split(".")[2]) == len(token.split(".")[2])


def test_status_matching_accepts_one_or_explicit_set() -> None:
    assert status_matches(401, 401)
    assert status_matches(503, {500, 503})
    assert not status_matches(403, {401, 409})


def test_retry_schedule_validates_5_30_120_persisted_delays() -> None:
    events = [
        {"event_type": "compensation_started", "occurred_at_epoch": 100.0},
        {"event_type": "retry_wait", "occurred_at_epoch": 101.0},
        {"event_type": "compensation_started", "occurred_at_epoch": 106.2},
        {"event_type": "retry_wait", "occurred_at_epoch": 107.0},
        {"event_type": "compensation_started", "occurred_at_epoch": 137.4},
        {"event_type": "retry_wait", "occurred_at_epoch": 150.0},
        {"event_type": "compensation_started", "occurred_at_epoch": 270.8},
    ]

    result = validate_retry_schedule(events)

    assert result["passed"] is True
    assert [item["expected_seconds"] for item in result["observations"]] == [5.0, 30.0, 120.0]


def test_retry_schedule_rejects_early_or_missing_attempts() -> None:
    events = [
        {"event_type": "retry_wait", "occurred_at_epoch": 10.0},
        {"event_type": "compensation_started", "occurred_at_epoch": 11.0},
    ]

    result = validate_retry_schedule(events)

    assert result["passed"] is False
    assert result["observations"][0]["passed"] is False
    assert result["observations"][1]["missing"] is True


def test_evidence_sanitizer_redacts_structured_and_embedded_secrets() -> None:
    jwt = _jwt({"sub": "alice", "tenant_id": "acme-corp"})
    dirty = {
        "access_token": jwt,
        "nested": {
            "password": "correct horse battery staple",
            "safe_key_id": "reference-kek-v2",
            "message": f"unexpected bearer {jwt}",
            "database": "postgresql://user:password@db/example",
        },
    }

    clean = sanitize_evidence(dirty)

    assert clean["access_token"] == "[REDACTED]"
    assert clean["nested"]["password"] == "[REDACTED]"
    assert clean["nested"]["safe_key_id"] == "reference-kek-v2"
    assert clean["nested"]["message"] == "[REDACTED]"
    assert clean["nested"]["database"] == "[REDACTED]"
    assert jwt not in json.dumps(clean)


def test_fault_evidence_shape_fails_closed_on_any_case() -> None:
    evidence = build_fault_evidence(
        suite="core",
        cases=[
            {"name": "one", "status": "passed", "details": {}},
            {"name": "two", "status": "failed", "details": {"error": "safe"}},
        ],
        generated_at="2026-07-12T00:00:00+00:00",
        prepared=True,
        reset=False,
    )

    assert evidence["schema"] == SCHEMA
    assert evidence["status"] == "failed"
    assert evidence["checks"] == {"all_cases_passed": False}
    assert evidence["destructive_reset_explicitly_requested"] is False
