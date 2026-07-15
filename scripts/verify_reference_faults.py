"""Run deterministic fault, concurrency, and key-rotation acceptance scenarios.

Suites are intentionally separated by runtime cost:

* ``core`` verifies identity fail-closed behavior, assignment and tenant
  isolation, PostgreSQL outage safety, prepared-effect reconciliation, and
  concurrent approval serialization.
* ``long`` verifies a killed 60-second lease holder is taken over and the
  persisted 5/30/120-second retry schedule.
* ``keys`` verifies wrong-KEK failure, admin-authorized retry, KEK rotation,
  online DEK rewrap, and recovery of an effect created under the old KEK.

Faults are armed only through container-local files.  The runner never writes
tokens, credentials, DSNs, key material, recovery data, or internal approvals
to evidence.  ``--reset`` is the only path that removes Docker volumes.
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import importlib
import json
import random
import re
import secrets
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import httpx

if __package__:
    sys.modules.setdefault(
        "verify_reference_e2e",
        importlib.import_module("scripts.verify_reference_e2e"),
    )
    _acceptance = importlib.import_module("scripts.reference_acceptance_lib")
else:
    _acceptance = importlib.import_module("reference_acceptance_lib")

AcceptanceFailure = _acceptance.AcceptanceFailure
ROOT = _acceptance.ROOT
RUNTIME = _acceptance.RUNTIME
ReferenceIdentity = _acceptance.ReferenceIdentity
arm = _acceptance.arm
business_metric = _acceptance.business_metric
compose = _acceptance.compose
sql = _acceptance.sql
wait_url = _acceptance.wait_url
write_json = _acceptance.write_json


SCHEMA = "xa-guard.reference-fault-acceptance.v1"
CONTROL_URL = "http://localhost:13000"
BUSINESS_URL = "http://localhost:13082"
KEYCLOAK_DISCOVERY_URL = (
    "http://localhost:13081/realms/xa-guard/.well-known/openid-configuration"
)
DEFAULT_SEED = 20_260_712
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$")
_JWT_TEXT = re.compile(r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}(?![A-Za-z0-9_-])")
_SENSITIVE_KEYS = re.compile(
    r"(?:^|_)(?:access_token|refresh_token|authorization|password|client_secret|secret|keyring|"
    r"database_url|dsn|recovery|internal_auth(?:orization)?|wrapped_dek|ciphertext)(?:$|_)",
    re.IGNORECASE,
)
_SENSITIVE_TEXT = re.compile(
    r"(?i)(?:bearer\s+[A-Za-z0-9._~-]+|postgres(?:ql)?://\S+|-----BEGIN [A-Z ]+PRIVATE KEY-----)"
)


class FaultAcceptanceFailure(AcceptanceFailure):
    """A safe, credential-free scenario failure."""


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def mutate_jwt_claim(token: str, claim: str, value: Any) -> str:
    """Change one JWT payload claim without resigning it (a forgery probe)."""

    try:
        header, payload, signature = token.split(".")
        claims = json.loads(_b64url_decode(payload))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("token is not a three-segment JWT") from exc
    if not isinstance(claims, dict) or not header or not signature:
        raise ValueError("token is not a three-segment JWT")
    claims[claim] = value
    encoded = _b64url_encode(
        json.dumps(claims, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    )
    return f"{header}.{encoded}.{signature}"


def mutate_jwt_signature(token: str) -> str:
    """Deterministically corrupt a JWT signature while preserving its shape."""

    try:
        header, payload, signature = token.split(".")
    except ValueError as exc:
        raise ValueError("token is not a three-segment JWT") from exc
    if not header or not payload or not signature:
        raise ValueError("token is not a three-segment JWT")
    # Change the first base64url symbol: unlike the final symbol, it cannot be
    # composed solely of unused padding bits.
    replacement = "A" if signature[0] != "A" else "B"
    return f"{header}.{payload}.{replacement}{signature[1:]}"


def status_matches(actual: int, expected: int | Iterable[int]) -> bool:
    """Pure status predicate used both by scenarios and unit tests."""

    allowed = {expected} if isinstance(expected, int) else {int(value) for value in expected}
    return int(actual) in allowed


def validate_retry_schedule(
    events: Sequence[dict[str, Any]],
    *,
    expected_seconds: Sequence[float] = (5.0, 30.0, 120.0),
    early_tolerance_seconds: float = 1.0,
    late_tolerance_seconds: float = 20.0,
) -> dict[str, Any]:
    """Verify every retry_wait is followed by a start at its persisted delay."""

    waits = [event for event in events if event.get("event_type") == "retry_wait"]
    starts = [event for event in events if event.get("event_type") == "compensation_started"]
    observations: list[dict[str, Any]] = []
    for index, expected in enumerate(expected_seconds):
        if index >= len(waits):
            observations.append({"retry": index + 1, "expected_seconds": expected, "missing": True})
            continue
        wait_at = float(waits[index]["occurred_at_epoch"])
        following = [
            float(event["occurred_at_epoch"])
            for event in starts
            if float(event["occurred_at_epoch"]) > wait_at
        ]
        if not following:
            observations.append({"retry": index + 1, "expected_seconds": expected, "missing": True})
            continue
        observed = min(following) - wait_at
        observations.append(
            {
                "retry": index + 1,
                "expected_seconds": expected,
                "observed_seconds": round(observed, 3),
                "passed": expected - early_tolerance_seconds
                <= observed
                <= expected + late_tolerance_seconds,
            }
        )
    passed = len(waits) == len(expected_seconds) and all(
        observation.get("passed") is True for observation in observations
    )
    return {"passed": passed, "observations": observations}


def sanitize_evidence(value: Any) -> Any:
    """Recursively redact credential-shaped fields and strings before writing."""

    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            cleaned[key] = "[REDACTED]" if _SENSITIVE_KEYS.search(key) else sanitize_evidence(item)
        return cleaned
    if isinstance(value, (list, tuple)):
        return [sanitize_evidence(item) for item in value]
    if isinstance(value, str):
        if _JWT_TEXT.search(value) or _SENSITIVE_TEXT.search(value):
            return "[REDACTED]"
        return value
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def build_fault_evidence(
    *,
    suite: str,
    cases: Sequence[dict[str, Any]],
    generated_at: str,
    prepared: bool,
    reset: bool,
) -> dict[str, Any]:
    passed = bool(cases) and all(case.get("status") == "passed" for case in cases)
    return sanitize_evidence(
        {
            "schema": SCHEMA,
            "generated_at": generated_at,
            "suite": suite,
            "stack_prepared_by_runner": prepared,
            "destructive_reset_explicitly_requested": reset,
            "methodology": {
                "fault_control": "one-shot files inside reference containers",
                "database_observation": "fixed, identifier-validated PostgreSQL queries",
                "worker_semantics": "at-least-once with downstream idempotency",
                "secrets_persisted": False,
                "raw_tokens_persisted": False,
            },
            "cases": list(cases),
            "checks": {"all_cases_passed": passed},
            "status": "passed" if passed else "failed",
        }
    )


def _safe_id(value: Any, label: str) -> str:
    candidate = str(value or "")
    if _IDENTIFIER.fullmatch(candidate) is None:
        raise FaultAcceptanceFailure(f"{label} is missing or malformed")
    return candidate


def _sql_text(value: str, label: str) -> str:
    return _safe_id(value, label)


def _query_int(query: str) -> int:
    value = sql(query)
    try:
        return int(value)
    except ValueError as exc:
        raise FaultAcceptanceFailure("PostgreSQL returned an invalid count") from exc


def _effect_count() -> int:
    return _query_int("SELECT count(*) FROM xa_effects")


def _effect_status(effect_id: str) -> str:
    effect = _sql_text(effect_id, "effect_id")
    return sql(f"SELECT status FROM xa_effects WHERE effect_id='{effect}'")


def _wait_for(
    predicate: Callable[[], Any],
    *,
    timeout: float,
    label: str,
    interval: float = 0.5,
) -> Any:
    deadline = time.monotonic() + timeout
    last: Any = None
    while time.monotonic() < deadline:
        last = predicate()
        if last:
            return last
        time.sleep(interval)
    raise FaultAcceptanceFailure(f"timed out waiting for {label}; last={last!r}")


def _expect_json(
    response: httpx.Response,
    expected: int | Iterable[int],
    label: str,
) -> dict[str, Any]:
    if not status_matches(response.status_code, expected):
        raise FaultAcceptanceFailure(f"{label} returned HTTP {response.status_code}")
    try:
        value = response.json()
    except ValueError as exc:
        raise FaultAcceptanceFailure(f"{label} returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise FaultAcceptanceFailure(f"{label} returned a non-object response")
    return value


def _ticket_body(label: str) -> dict[str, str]:
    return {
        "title": f"Fault acceptance {label}",
        "description": f"Deterministic reference scenario {label}",
        "priority": "normal",
        "data_domain": "engineering_docs",
    }


def _create_ticket(token: str, label: str) -> dict[str, Any]:
    with httpx.Client(timeout=20) as client:
        return _expect_json(
            client.post(
                CONTROL_URL + "/control/v1/tickets",
                headers=ReferenceIdentity.headers(token),
                json=_ticket_body(label),
            ),
            201,
            "ticket creation",
        )


def _request_undo(token: str, effect_id: str, label: str) -> str:
    effect = _safe_id(effect_id, "effect_id")
    with httpx.Client(timeout=20) as client:
        value = _expect_json(
            client.post(
                f"{CONTROL_URL}/control/v1/effects/{effect}/undo-requests",
                headers=ReferenceIdentity.headers(
                    token,
                    idempotency_key=f"fault-undo-{label}-{effect}",
                ),
                json={"reason": f"Fault acceptance recovery {label}."},
            ),
            201,
            "Undo request",
        )
    return _safe_id(value.get("request_id"), "request_id")


def _decision(token: str, request_id: str, *, reason: str, expected: int = 200) -> dict[str, Any]:
    request = _safe_id(request_id, "request_id")
    with httpx.Client(timeout=20) as client:
        return _expect_json(
            client.post(
                f"{CONTROL_URL}/control/v1/undo-requests/{request}/decision",
                headers=ReferenceIdentity.headers(token),
                json={"decision": "approve", "reason": reason},
            ),
            expected,
            "Undo decision",
        )


def _wait_effect(effect_id: str, status: str, timeout: float) -> str:
    return _wait_for(
        lambda: status if _effect_status(effect_id) == status else "",
        timeout=timeout,
        label=f"effect {effect_id} -> {status}",
    )


def _metric(operation: str) -> int:
    return business_metric(
        "xa_reference_business_attempts_total",
        f'operation="{operation}"',
    )


def _effective_cancels() -> int:
    return business_metric(
        "xa_reference_business_effective_transitions_total",
        'transition="open_to_cancelled"',
    )


def _identity_rejections(identity: Any) -> dict[str, Any]:
    alice = identity.agent_token("alice")
    human = identity.human_token("alice")
    before_effects = _effect_count()
    before_business = _metric("create")
    probes: list[tuple[str, str | None]] = [
        ("unauthenticated", None),
        ("malformed", "not-a-jwt"),
        ("bad_signature", mutate_jwt_signature(alice)),
        ("wrong_audience", human),
        ("forged_sub", mutate_jwt_claim(alice, "sub", "90000000-0000-0000-0000-000000000009")),
        ("forged_azp", mutate_jwt_claim(alice, "azp", "finance-agent")),
        ("forged_tenant", mutate_jwt_claim(alice, "tenant_id", "beta-corp")),
    ]
    statuses: dict[str, int] = {}
    with httpx.Client(timeout=20) as client:
        for name, token in probes:
            headers = ReferenceIdentity.headers(token) if token else {}
            response = client.post(
                CONTROL_URL + "/control/v1/tickets",
                headers=headers,
                json=_ticket_body(f"identity-{name}"),
            )
            statuses[name] = response.status_code
            if response.status_code != 401:
                raise FaultAcceptanceFailure(
                    f"identity probe {name} returned HTTP {response.status_code}, expected 401"
                )
    after_effects = _effect_count()
    after_business = _metric("create")
    if (after_effects, after_business) != (before_effects, before_business):
        raise FaultAcceptanceFailure("an identity rejection reached effect or business execution")
    return {
        "probe_statuses": statuses,
        "effect_delta": after_effects - before_effects,
        "business_create_attempt_delta": after_business - before_business,
    }


def _header_binding(identity: Any) -> dict[str, Any]:
    alice = identity.agent_token("alice")
    headers = ReferenceIdentity.headers(alice, agent_id="finance-agent")
    headers.update(
        {
            "X-Human-Principal": "90000000-0000-0000-0000-000000000009",
            "X-Tenant-ID": "beta-corp",
            "X-Subject": "forged-subject",
        }
    )
    with httpx.Client(timeout=20) as client:
        me = _expect_json(client.get(CONTROL_URL + "/control/v1/me", headers=headers), 200, "identity")
    expected = {
        "subject": "10000000-0000-0000-0000-000000000001",
        "tenant_id": "acme-corp",
        "agent_id": "general-office-agent",
    }
    actual = {key: me.get(key) for key in expected}
    if actual != expected:
        raise FaultAcceptanceFailure("request identity headers overrode signed token claims")
    return {"signed_identity": actual, "spoof_headers_ignored": True}


def _find_engineering_assignment(admin_token: str) -> dict[str, Any] | None:
    with httpx.Client(timeout=20) as client:
        value = _expect_json(
            client.get(
                CONTROL_URL + "/control/v1/assignments",
                headers=ReferenceIdentity.headers(admin_token),
            ),
            200,
            "assignment list",
        )
    for item in value.get("items", []):
        if (
            item.get("subject_type") == "group"
            and item.get("subject_id") == "engineering-team"
            and item.get("agent_id") == "general-office-agent"
        ):
            return dict(item)
    return None


def _restore_engineering_assignment(admin_token: str) -> dict[str, Any]:
    existing = _find_engineering_assignment(admin_token)
    if existing is not None:
        return existing
    with httpx.Client(timeout=20) as client:
        return _expect_json(
            client.post(
                CONTROL_URL + "/control/v1/assignments",
                headers={
                    **ReferenceIdentity.headers(admin_token),
                    "If-None-Match": "*",
                },
                json={
                    "subject_type": "group",
                    "subject_id": "engineering-team",
                    "agent_id": "general-office-agent",
                    "tools": ["business_submit_ticket"],
                    "data_domains": ["engineering_docs"],
                },
            ),
            201,
            "assignment restore",
        )


def _assignment_revocation(identity: Any) -> dict[str, Any]:
    alice = identity.agent_token("alice")
    admin = identity.agent_token("governance_admin")
    assignment = _find_engineering_assignment(admin)
    if assignment is None:
        assignment = _restore_engineering_assignment(admin)
    assignment_id = _safe_id(assignment.get("assignment_id"), "assignment_id")
    version = int(assignment.get("version") or 0)
    before_effects = _effect_count()
    before_business = _metric("create")
    deleted = False
    denied_status = 0
    try:
        with httpx.Client(timeout=20) as client:
            response = client.delete(
                f"{CONTROL_URL}/control/v1/assignments/{assignment_id}",
                headers={
                    **ReferenceIdentity.headers(admin),
                    "If-Match": f'"v{version}"',
                },
            )
            if response.status_code != 204:
                raise FaultAcceptanceFailure(
                    f"assignment revoke returned HTTP {response.status_code}"
                )
            deleted = True
            denied = client.post(
                CONTROL_URL + "/control/v1/tickets",
                headers=ReferenceIdentity.headers(alice),
                json=_ticket_body("revoked-assignment"),
            )
            denied_status = denied.status_code
            if denied.status_code != 403:
                raise FaultAcceptanceFailure(
                    f"revoked assignment write returned HTTP {denied.status_code}"
                )
        if _effect_count() != before_effects or _metric("create") != before_business:
            raise FaultAcceptanceFailure("revoked assignment reached effect or business execution")
    finally:
        if deleted:
            _restore_engineering_assignment(admin)
    restored = _find_engineering_assignment(admin)
    if restored is None:
        raise FaultAcceptanceFailure("engineering assignment was not restored")
    return {
        "denied_status": denied_status,
        "effect_delta": _effect_count() - before_effects,
        "business_create_attempt_delta": _metric("create") - before_business,
        "restored_assignment_version": int(restored["version"]),
    }


def _tenant_isolation(identity: Any) -> dict[str, Any]:
    alice = identity.agent_token("alice")
    dora = identity.agent_token("dora")
    eve = identity.agent_token(
        "eve",
        agent_id="beta-ops-agent",
        secret_name="beta_agent_client_secret",
    )
    created = _create_ticket(alice, f"tenant-{uuid.uuid4().hex[:10]}")
    effect_id = _safe_id(created.get("effect_id"), "effect_id")
    request_id = _request_undo(alice, effect_id, "tenant-isolation")
    beta_headers = ReferenceIdentity.headers(eve, agent_id="beta-ops-agent")
    try:
        with httpx.Client(timeout=20) as client:
            effects = _expect_json(
                client.get(CONTROL_URL + "/control/v1/effects", headers=beta_headers),
                200,
                "beta effect list",
            )
            beta_effects = list(effects.get("items") or [])
            if any(item.get("tenant_id") != "beta-corp" for item in beta_effects):
                raise FaultAcceptanceFailure("beta effect list disclosed a foreign tenant")
            detail = client.get(
                f"{CONTROL_URL}/control/v1/effects/{effect_id}",
                headers=beta_headers,
            )
            if detail.status_code != 404:
                raise FaultAcceptanceFailure(
                    f"beta cross-tenant effect detail returned HTTP {detail.status_code}"
                )
            pending = _expect_json(
                client.get(
                    CONTROL_URL + "/control/v1/undo-requests?status=pending",
                    headers=beta_headers,
                ),
                200,
                "beta pending queue",
            )
            pending_ids = {item.get("request_id") for item in pending.get("items", [])}
            if request_id in pending_ids or any(
                item.get("tenant_id") != "beta-corp" for item in pending.get("items", [])
            ):
                raise FaultAcceptanceFailure("beta approval queue disclosed a foreign tenant")
    finally:
        with httpx.Client(timeout=20) as client:
            cleanup = client.post(
                f"{CONTROL_URL}/control/v1/undo-requests/{request_id}/decision",
                headers=ReferenceIdentity.headers(dora),
                json={"decision": "reject", "reason": "Tenant isolation cleanup."},
            )
            if cleanup.status_code not in {200, 409}:
                raise FaultAcceptanceFailure("tenant isolation cleanup decision failed")
    return {
        "beta_effect_count": len(beta_effects),
        "foreign_effect_detail_status": detail.status_code,
        "foreign_request_absent": True,
    }


def _wait_postgres() -> None:
    def ready() -> bool:
        result = compose(
            "exec",
            "-T",
            "postgres",
            "pg_isready",
            "-U",
            "xaguard",
            "-d",
            "xaguard",
            check=False,
        )
        return result.returncode == 0

    _wait_for(ready, timeout=90, label="PostgreSQL readiness", interval=1)


def _postgres_fail_closed(identity: Any) -> dict[str, Any]:
    alice = identity.agent_token("alice")
    before_effects = _effect_count()
    before_business = _metric("create")
    response_status: int | str = "transport_failure"
    compose("stop", "postgres")
    try:
        with httpx.Client(timeout=15) as client:
            try:
                response = client.post(
                    CONTROL_URL + "/control/v1/tickets",
                    headers=ReferenceIdentity.headers(alice),
                    json=_ticket_body("postgres-unavailable"),
                )
                response_status = response.status_code
                if response.status_code < 500:
                    raise FaultAcceptanceFailure(
                        f"write during PostgreSQL outage returned HTTP {response.status_code}"
                    )
            except httpx.HTTPError:
                response_status = "transport_failure"
        if _metric("create") != before_business:
            raise FaultAcceptanceFailure("business API was called while effect storage was unavailable")
    finally:
        compose("start", "postgres")
        _wait_postgres()
        wait_url(KEYCLOAK_DISCOVERY_URL, timeout=90)
        wait_url(BUSINESS_URL + "/readyz", timeout=90)
        wait_url(CONTROL_URL + "/readyz", timeout=90)
    after_effects = _effect_count()
    if after_effects != before_effects:
        raise FaultAcceptanceFailure("PostgreSQL outage created an effect unexpectedly")
    return {
        "write_result": response_status,
        "effect_delta": after_effects - before_effects,
        "business_create_attempt_delta": _metric("create") - before_business,
        "recovered": True,
    }


def _prepared_reconciliation(identity: Any) -> dict[str, Any]:
    alice = identity.agent_token("alice")
    label = f"crash-{uuid.uuid4().hex[:16]}"
    before_business = _metric("create")
    arm("xa-guard", "after_create_success_before_effect_complete")
    with httpx.Client(timeout=20) as client:
        try:
            response = client.post(
                CONTROL_URL + "/control/v1/tickets",
                headers=ReferenceIdentity.headers(alice),
                json=_ticket_body(label),
            )
            if response.status_code < 500:
                raise FaultAcceptanceFailure(
                    f"armed crash request unexpectedly returned HTTP {response.status_code}"
                )
        except httpx.HTTPError:
            pass
    wait_url(CONTROL_URL + "/readyz", timeout=90)
    effect_id = _wait_for(
        lambda: sql(
            "SELECT create_effect_id FROM xa_reference_tickets "
            f"WHERE title='Fault acceptance {label}' ORDER BY created_at DESC LIMIT 1"
        ),
        timeout=30,
        label="downstream ticket after API crash",
    )
    effect_id = _safe_id(effect_id, "effect_id")
    initial_status = _effect_status(effect_id)
    if initial_status != "prepared":
        raise FaultAcceptanceFailure(
            f"crash-window effect was not prepared before reconciliation: {initial_status}"
        )
    _wait_effect(effect_id, "available", timeout=95)
    if _metric("create") - before_business != 1:
        raise FaultAcceptanceFailure("crash-window downstream create was not exactly one attempt")
    ticket_count = _query_int(
        "SELECT count(*) FROM xa_reference_tickets "
        f"WHERE create_effect_id='{effect_id}'"
    )
    if ticket_count != 1:
        raise FaultAcceptanceFailure("reconciled effect did not map to exactly one ticket")
    return {
        "effect_id": effect_id,
        "initial_status": initial_status,
        "final_status": "available",
        "business_create_attempt_delta": 1,
        "ticket_count": ticket_count,
    }


def _double_approval(identity: Any) -> dict[str, Any]:
    alice = identity.agent_token("alice")
    dora = identity.agent_token("dora")
    created = _create_ticket(alice, f"double-{uuid.uuid4().hex[:10]}")
    effect_id = _safe_id(created.get("effect_id"), "effect_id")
    request_id = _request_undo(alice, effect_id, "double-approval")
    barrier = threading.Barrier(2)

    def decide(index: int) -> int:
        barrier.wait(timeout=10)
        with httpx.Client(timeout=25) as client:
            return client.post(
                f"{CONTROL_URL}/control/v1/undo-requests/{request_id}/decision",
                headers=ReferenceIdentity.headers(dora),
                json={
                    "decision": "approve",
                    "reason": f"Concurrent independent approval {index}.",
                },
            ).status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        statuses = sorted(executor.map(decide, (1, 2)))
    if statuses != [200, 409]:
        raise FaultAcceptanceFailure(f"concurrent decisions returned {statuses}, expected [200, 409]")
    approved_events = _query_int(
        "SELECT count(*) FROM xa_effect_events "
        f"WHERE effect_id='{effect_id}' AND event_type='undo_approved'"
    )
    request_rows = _query_int(
        f"SELECT count(*) FROM xa_undo_requests WHERE request_id='{request_id}'"
    )
    _wait_effect(effect_id, "compensated", timeout=45)
    if approved_events != 1 or request_rows != 1:
        raise FaultAcceptanceFailure("concurrent approval created more than one logical task")
    return {
        "http_statuses": statuses,
        "undo_approved_events": approved_events,
        "logical_request_rows": request_rows,
        "final_status": "compensated",
    }


def _set_workers(count: int, *, force_recreate: bool = False) -> None:
    if count == 0:
        compose("stop", "worker")
        return
    args = ["up", "-d", "--scale", f"worker={count}"]
    if force_recreate:
        args.extend(["--force-recreate", "--no-deps"])
    args.append("worker")
    compose(*args)


def _docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=check,
    )


def _worker_containers() -> dict[str, str]:
    result = compose("ps", "-q", "worker")
    mapping: dict[str, str] = {}
    for container_id in result.stdout.splitlines():
        candidate = container_id.strip()
        if not candidate:
            continue
        hostname = _docker("inspect", "--format", "{{.Config.Hostname}}", candidate).stdout.strip()
        mapping[_safe_id(hostname, "worker hostname")] = _safe_id(candidate, "container_id")
    return mapping


def _worker_lease_takeover(identity: Any) -> dict[str, Any]:
    _set_workers(2, force_recreate=True)
    _wait_for(lambda: len(_worker_containers()) == 2, timeout=45, label="two workers")
    alice = identity.agent_token("alice")
    dora = identity.agent_token("dora")
    created = _create_ticket(alice, f"lease-{uuid.uuid4().hex[:10]}")
    effect_id = _safe_id(created.get("effect_id"), "effect_id")
    request_id = _request_undo(alice, effect_id, "lease-takeover")
    before_effective = _effective_cancels()
    arm("business-api", "after_cancel_commit", "120")
    _decision(dora, request_id, reason="Lease takeover acceptance approval.")

    def committed_and_leased() -> str:
        return sql(
            "SELECT e.lease_owner FROM xa_effects e "
            "JOIN xa_reference_tickets t ON t.create_effect_id=e.effect_id "
            f"WHERE e.effect_id='{effect_id}' AND e.status='compensating' "
            "AND t.state='cancelled' AND e.lease_owner IS NOT NULL"
        )

    lease_owner = _safe_id(
        _wait_for(committed_and_leased, timeout=35, label="cancel commit under active lease"),
        "lease_owner",
    )
    workers = _worker_containers()
    holder_hostname = next((host for host in workers if lease_owner.startswith(host)), "")
    if not holder_hostname:
        raise FaultAcceptanceFailure("active lease owner did not map to a worker container")
    holder = workers[holder_hostname]
    try:
        _docker("update", "--restart=no", holder)
        _docker("kill", holder)
        _wait_effect(effect_id, "compensated", timeout=105)
        actors_raw = sql(
            "SELECT string_agg(actor_sub,'|' ORDER BY seq) FROM xa_effect_events "
            f"WHERE effect_id='{effect_id}' AND event_type='compensation_started'"
        )
        actors = [_safe_id(actor, "worker event actor") for actor in actors_raw.split("|") if actor]
        if len(set(actors)) < 2 or not any(not actor.startswith(holder_hostname) for actor in actors):
            raise FaultAcceptanceFailure("another worker did not take over the expired lease")
        effective_delta = _effective_cancels() - before_effective
        if effective_delta != 1:
            raise FaultAcceptanceFailure("lease takeover produced more than one effective cancellation")
    finally:
        _docker("update", "--restart=unless-stopped", holder, check=False)
        _set_workers(1, force_recreate=True)
    return {
        "effect_id": effect_id,
        "killed_lease_holder": holder_hostname,
        "distinct_worker_actors": len(set(actors)),
        "effective_cancel_delta": effective_delta,
        "final_status": "compensated",
    }


def _effect_events(effect_id: str) -> list[dict[str, Any]]:
    effect = _sql_text(effect_id, "effect_id")
    rows = sql(
        "SELECT event_type || '|' || extract(epoch FROM occurred_at)::text "
        f"FROM xa_effect_events WHERE effect_id='{effect}' ORDER BY seq"
    )
    events: list[dict[str, Any]] = []
    for row in rows.splitlines():
        parts = row.split("|")
        if len(parts) != 2:
            raise FaultAcceptanceFailure("effect event query returned an invalid shape")
        events.append({"event_type": parts[0], "occurred_at_epoch": float(parts[1])})
    return events


def _retry_schedule(identity: Any) -> dict[str, Any]:
    _set_workers(1, force_recreate=True)
    alice = identity.agent_token("alice")
    dora = identity.agent_token("dora")
    created = _create_ticket(alice, f"retry-{uuid.uuid4().hex[:10]}")
    effect_id = _safe_id(created.get("effect_id"), "effect_id")
    request_id = _request_undo(alice, effect_id, "retry-schedule")
    plan = {
        "steps": [
            {"mode": "response", "status": 429},
            {"mode": "response", "status": 503},
            {"mode": "timeout", "seconds": 12},
            {"mode": "normal"},
        ]
    }
    before_effective = _effective_cancels()
    arm("business-api", "cancel_response_plan", json.dumps(plan, separators=(",", ":")))
    _decision(dora, request_id, reason="Persisted retry schedule acceptance approval.")
    _wait_effect(effect_id, "compensated", timeout=205)
    events = _effect_events(effect_id)
    schedule = validate_retry_schedule(events)
    retry_count = _query_int(
        f"SELECT retry_count FROM xa_effects WHERE effect_id='{effect_id}'"
    )
    effective_delta = _effective_cancels() - before_effective
    if not schedule["passed"] or retry_count != 3 or effective_delta != 1:
        raise FaultAcceptanceFailure("5/30/120 retry schedule or effective-once outcome failed")
    return {
        "effect_id": effect_id,
        "retry_count": retry_count,
        "schedule": schedule,
        "effective_cancel_delta": effective_delta,
        "final_status": "compensated",
    }


def _keyring_path() -> Path:
    return RUNTIME / "secrets" / "kek_keyring"


def _read_keyring() -> dict[str, Any]:
    try:
        value = json.loads(_keyring_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FaultAcceptanceFailure("reference keyring is unavailable or malformed") from exc
    if not isinstance(value, dict) or not isinstance(value.get("keys"), dict) or not value.get("active"):
        raise FaultAcceptanceFailure("reference keyring has an invalid shape")
    return value


def _write_keyring(value: dict[str, Any]) -> None:
    path = _keyring_path()
    temporary = path.with_suffix(".acceptance-tmp")
    temporary.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _wrong_kek_retry(identity: Any) -> dict[str, Any]:
    original = _read_keyring()
    active = _safe_id(original.get("active"), "active key id")
    alice = identity.agent_token("alice")
    dora = identity.agent_token("dora")
    _set_workers(0)
    effect_id = ""
    request_id = ""
    failed_status = ""
    try:
        created = _create_ticket(alice, f"wrong-kek-{uuid.uuid4().hex[:10]}")
        effect_id = _safe_id(created.get("effect_id"), "effect_id")
        request_id = _request_undo(alice, effect_id, "wrong-kek")
        _decision(dora, request_id, reason="Wrong KEK fail-closed acceptance approval.")
        wrong = {
            "active": active,
            "keys": {active: base64.b64encode(secrets.token_bytes(32)).decode("ascii")},
        }
        _write_keyring(wrong)
        _set_workers(1, force_recreate=True)
        _wait_effect(effect_id, "compensation_failed", timeout=45)
        failed_status = _effect_status(effect_id)
    finally:
        _write_keyring(original)
        _set_workers(1, force_recreate=True)
    admin = identity.agent_token("governance_admin")
    with httpx.Client(timeout=20) as client:
        _expect_json(
            client.post(
                f"{CONTROL_URL}/control/v1/undo-requests/{request_id}/retry",
                headers=ReferenceIdentity.headers(admin),
                json={},
            ),
            200,
            "admin retry after KEK restore",
        )
    _wait_effect(effect_id, "compensated", timeout=45)
    return {
        "effect_id": effect_id,
        "record_key_id": active,
        "wrong_key_status": failed_status,
        "admin_retry_authorized": True,
        "final_status": "compensated",
    }


def _restart_api_and_worker() -> None:
    compose(
        "up",
        "-d",
        "--force-recreate",
        "--no-deps",
        "--scale",
        "worker=1",
        "xa-guard",
        "worker",
    )
    wait_url(CONTROL_URL + "/readyz", timeout=90)


def _rotate_rewrap(identity: Any) -> dict[str, Any]:
    original = _read_keyring()
    old_id = _safe_id(original.get("active"), "old key id")
    alice = identity.agent_token("alice")
    created = _create_ticket(alice, f"rewrap-{uuid.uuid4().hex[:10]}")
    effect_id = _safe_id(created.get("effect_id"), "effect_id")
    stored_old = _safe_id(
        sql(f"SELECT key_id FROM xa_effects WHERE effect_id='{effect_id}'"),
        "stored old key id",
    )
    if stored_old != old_id:
        raise FaultAcceptanceFailure("new effect did not use the active pre-rotation KEK")

    suffix = 2
    while f"reference-kek-v{suffix}" in original["keys"]:
        suffix += 1
    new_id = f"reference-kek-v{suffix}"
    rotated = {
        "active": new_id,
        "keys": {
            **dict(original["keys"]),
            new_id: base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
        },
    }
    _write_keyring(rotated)
    _restart_api_and_worker()
    result = compose(
        "run",
        "--rm",
        "--no-deps",
        "xa-guard",
        "python",
        "-m",
        "xa_guard.control.rewrap",
        "--batch-size",
        "100",
    )
    try:
        rewrap_result = json.loads(result.stdout.splitlines()[-1])
        rewrapped = int(rewrap_result["rewrapped"])
    except (IndexError, KeyError, ValueError, json.JSONDecodeError) as exc:
        raise FaultAcceptanceFailure("online rewrap returned an invalid result") from exc
    stored_new = _safe_id(
        sql(f"SELECT key_id FROM xa_effects WHERE effect_id='{effect_id}'"),
        "stored new key id",
    )
    if stored_new != new_id or rewrapped < 1 or old_id not in rotated["keys"]:
        raise FaultAcceptanceFailure("online rewrap did not preserve and rotate the old record")
    alice = identity.agent_token("alice")
    dora = identity.agent_token("dora")
    request_id = _request_undo(alice, effect_id, "rotated-rewrap")
    _decision(dora, request_id, reason="Rotated KEK recovery acceptance approval.")
    _wait_effect(effect_id, "compensated", timeout=45)
    return {
        "effect_id": effect_id,
        "old_key_id": old_id,
        "new_key_id": new_id,
        "old_key_preserved": True,
        "rewrapped_records": rewrapped,
        "record_key_id_after_rewrap": stored_new,
        "old_created_record_final_status": "compensated",
    }


def _run_case(name: str, callback: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    started = time.monotonic()
    try:
        details = callback()
        status = "passed"
    except Exception as exc:  # noqa: BLE001 - continue to preserve all acceptance observations
        details = {"error_type": type(exc).__name__, "error": str(exc)}
        status = "failed"
    return sanitize_evidence(
        {
            "name": name,
            "status": status,
            "duration_seconds": round(time.monotonic() - started, 3),
            "details": details,
        }
    )


def _prepare_stack(*, reset: bool) -> None:
    if reset:
        compose("down", "-v", "--remove-orphans", check=False)
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "reference_stack.py"), "bootstrap"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise FaultAcceptanceFailure("reference bootstrap failed")
    # BuildKit may emit UTF-8 progress text that Windows' legacy subprocess
    # locale cannot decode through a captured pipe.  Stream it directly; it
    # contains build progress only, never generated runtime secrets.
    compose("up", "-d", "--build", capture=False)


def _require_reference_ready() -> None:
    wait_url(BUSINESS_URL + "/readyz", timeout=120)
    wait_url(CONTROL_URL + "/readyz", timeout=120)
    _wait_postgres()
    result = compose(
        "exec",
        "-T",
        "xa-guard",
        "python",
        "-c",
        "import os; print(os.getenv('XA_GUARD_TEST_FAULTS','false').lower())",
    )
    if result.stdout.strip() not in {"1", "true", "yes", "on"}:
        raise FaultAcceptanceFailure(
            "reference services were not started with XA_GUARD_TEST_FAULTS=true; use --prepare"
        )


def _suite_cases(suite: str, identity: Any) -> list[tuple[str, Callable[[], dict[str, Any]]]]:
    core = [
        ("identity_rejections_before_execution", lambda: _identity_rejections(identity)),
        ("signed_identity_ignores_spoof_headers", lambda: _header_binding(identity)),
        ("assignment_revocation_is_immediate", lambda: _assignment_revocation(identity)),
        ("cross_tenant_effect_and_queue_isolation", lambda: _tenant_isolation(identity)),
        ("postgresql_unavailable_calls_no_business", lambda: _postgres_fail_closed(identity)),
        ("prepared_effect_reconciles_after_api_crash", lambda: _prepared_reconciliation(identity)),
        ("concurrent_double_approval_is_one_task", lambda: _double_approval(identity)),
    ]
    long = [
        ("killed_worker_lease_is_taken_over", lambda: _worker_lease_takeover(identity)),
        ("retry_schedule_5_30_120_is_effective_once", lambda: _retry_schedule(identity)),
    ]
    keys = [
        ("wrong_kek_fails_then_admin_retry_recovers", lambda: _wrong_kek_retry(identity)),
        ("kek_rotation_rewrap_preserves_old_record", lambda: _rotate_rewrap(identity)),
    ]
    return {"core": core, "long": long, "keys": keys, "all": core + long + keys}[suite]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=("core", "long", "keys", "all"), default="core")
    parser.add_argument(
        "--prepare",
        action="store_true",
        help="bootstrap/build/reconcile the reference stack with fault hooks enabled",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="explicitly remove Compose volumes before preparing the stack",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--output", type=Path)
    return parser


def main() -> None:
    args = _parser().parse_args()
    random.seed(args.seed)
    output = args.output or (
        ROOT / ".runtime" / "evidence" / f"reference-faults-{args.suite}.json"
    )
    prepared = bool(args.prepare or args.reset)
    try:
        if prepared:
            _prepare_stack(reset=args.reset)
        _require_reference_ready()
        identity = ReferenceIdentity(control_url=CONTROL_URL)
        cases = [
            _run_case(name, callback)
            for name, callback in _suite_cases(args.suite, identity)
        ]
        evidence = build_fault_evidence(
            suite=args.suite,
            cases=cases,
            generated_at=datetime.now(timezone.utc).isoformat(),
            prepared=prepared,
            reset=args.reset,
        )
        write_json(output.resolve(), evidence)
    except (OSError, ValueError, KeyError, httpx.HTTPError, AcceptanceFailure) as exc:
        raise SystemExit(f"REFERENCE FAULT ACCEPTANCE FAILED: {exc}") from None
    print(
        json.dumps(
            {
                "schema": evidence["schema"],
                "suite": evidence["suite"],
                "status": evidence["status"],
                "output": str(output.resolve()),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    if evidence["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
