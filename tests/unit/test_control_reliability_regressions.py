from __future__ import annotations

import asyncio
import base64
import json
from types import SimpleNamespace
from typing import Any

import pytest

import xa_guard.control.crypto as crypto_module
import xa_guard.control.oidc as oidc_module
from xa_guard.control.crypto import CryptoError, InternalAuthorization, Keyring, sha256_json
from xa_guard.control.models import Principal
from xa_guard.control.oidc import OIDCError, OIDCSettings, OIDCVerifier
from xa_guard.control.service import ControlService
from xa_guard.control.store import AsyncEffectStore
from xa_guard.control.worker import CompensationWorker


class _LeaseLostStore:
    def __init__(self) -> None:
        self.failure_writes = 0

    async def claim_work(self, _worker_id: str, _lease_seconds: int) -> dict[str, Any]:
        return {"effect_id": "eff-lease-lost"}

    async def heartbeat(self, _effect_id: str, _worker_id: str, _lease_seconds: int) -> bool:
        return False

    async def fail_work(self, *_args: Any) -> None:
        self.failure_writes += 1


class _SlowCompensationWorker(CompensationWorker):
    def __init__(self, runtime: Any) -> None:
        super().__init__(runtime, worker_id="worker-a")
        self.heartbeat_seconds = 0
        self.was_cancelled = False

    async def _compensate(self, _row: dict[str, Any]) -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.was_cancelled = True
            raise


def test_heartbeat_lease_loss_cancels_compensation_without_stale_state_write() -> None:
    store = _LeaseLostStore()
    worker = _SlowCompensationWorker(SimpleNamespace(store=store))

    assert asyncio.run(worker.run_once()) is True
    assert worker.was_cancelled is True
    assert store.failure_writes == 0


def test_expired_internal_authorization_can_only_be_recovered_for_admin_resigning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signer = InternalAuthorization(b"k" * 32)
    monkeypatch.setattr(crypto_module.time, "time", lambda: 1_000)
    old = signer.issue({"effect_id": "eff-1", "request_id": "undo-1"}, ttl_seconds=60)
    monkeypatch.setattr(crypto_module.time, "time", lambda: 5_000)

    with pytest.raises(CryptoError):
        signer.verify(old)
    recovered = signer.verify_for_admin_retry(
        old, {"effect_id": "eff-1", "request_id": "undo-1"}
    )
    fresh = signer.issue(
        {"effect_id": recovered["effect_id"], "request_id": recovered["request_id"]},
        ttl_seconds=60,
    )
    assert signer.verify(fresh)["effect_id"] == "eff-1"


class _RetryStore:
    def __init__(self, request: dict[str, Any]) -> None:
        self.request = request
        self.saved: tuple[Any, ...] | None = None

    async def get_undo_request(self, _tenant_id: str, _request_id: str) -> dict[str, Any]:
        return dict(self.request)

    async def authorize(self, *_args: Any) -> dict[str, Any]:
        return {"assignment_id": "asg-admin"}

    async def retry_failed(self, *args: Any) -> None:
        self.saved = args


def test_admin_retry_resigns_expired_approval_with_current_bounded_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signer = InternalAuthorization(b"s" * 32)
    parameters = {"reason": "approved cancellation"}
    args_hash = sha256_json(parameters)
    monkeypatch.setattr(crypto_module.time, "time", lambda: 1_000)
    old = signer.issue(
        {
            "effect_id": "eff-1",
            "request_id": "undo-1",
            "approver_sub": "dora-id",
            "approver_username": "dora",
            "tenant_id": "acme",
            "agent_id": "general-office-agent",
            "parameters": parameters,
            "parameters_sha256": args_hash,
        },
        ttl_seconds=60,
    )
    store = _RetryStore(
        {
            "effect_id": "eff-1",
            "approver_sub": "dora-id",
            "approver_username": "dora",
            "data_domain": "engineering_docs",
            "contract_snapshot": {"compensation_tool": "business_cancel_ticket"},
            "internal_authorization": old,
            "compensation_args_sha256": args_hash,
        }
    )
    ceiling_agent = SimpleNamespace(
        tenant_id="acme",
        tools=("business_cancel_ticket",),
        data_domains=("engineering_docs",),
    )
    service = ControlService(
        store=store,  # type: ignore[arg-type]
        business=SimpleNamespace(),
        pipeline=SimpleNamespace(),
        contracts=SimpleNamespace(),
        ceiling=SimpleNamespace(agents={"general-office-agent": ceiling_agent}),
        internal_authorization=signer,
    )
    admin = Principal(
        subject="admin-id",
        username="admin",
        tenant_id="acme",
        agent_id="general-office-agent",
        issuer="https://id.example",
        token_id_hash="hash",
        roles=("undo.admin",),
        groups=("governance-admins",),
    )
    monkeypatch.setattr(crypto_module.time, "time", lambda: 5_000)

    asyncio.run(service.retry_failed(admin, "undo-1"))

    assert store.saved is not None
    tenant_id, request_id, actor, renewed, saved_hash = store.saved
    assert (tenant_id, request_id, actor, saved_hash) == (
        "acme",
        "undo-1",
        "admin-id",
        args_hash,
    )
    claims = signer.verify(
        renewed,
        {
            "effect_id": "eff-1",
            "request_id": "undo-1",
            "approver_sub": "dora-id",
            "parameters_sha256": args_hash,
        },
    )
    assert claims["authorization_sub"] == "admin-id"
    assert claims["approver_sub"] == "dora-id"
    assert claims["exp"] - claims["iat"] == 900


class _Transaction:
    def __init__(self, connection: "_Connection") -> None:
        self.connection = connection

    async def __aenter__(self) -> None:
        self.connection.transaction_count += 1

    async def __aexit__(self, *_args: Any) -> None:
        return None


class _Connection:
    def __init__(self) -> None:
        self.transaction_count = 0
        self.executed: list[str] = []

    def transaction(self) -> _Transaction:
        return _Transaction(self)

    async def fetchrow(self, _query: str, *_args: Any) -> dict[str, str]:
        return {
            "effect_id": "eff-1",
            "effect_status": "compensation_failed",
            "request_status": "failed",
        }

    async def execute(self, query: str, *_args: Any) -> None:
        self.executed.append(" ".join(query.split()))

    async def fetchval(self, _query: str, *_args: Any) -> str:
        return ""


class _Acquire:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    async def __aenter__(self) -> _Connection:
        return self.connection

    async def __aexit__(self, *_args: Any) -> None:
        return None


class _Pool:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    def acquire(self) -> _Acquire:
        return _Acquire(self.connection)


def test_manual_retry_effect_request_and_event_share_one_transaction() -> None:
    connection = _Connection()
    store = AsyncEffectStore("postgresql://unused", Keyring({"v1": b"k" * 32}, "v1"))
    store.pool = _Pool(connection)

    asyncio.run(
        store.retry_failed(
            "acme", "undo-1", "admin-id", "signed-authorization", "args-hash"
        )
    )

    assert connection.transaction_count == 1
    assert any("UPDATE xa_effects" in query for query in connection.executed)
    assert any("UPDATE xa_undo_requests" in query for query in connection.executed)
    assert any("INSERT INTO xa_effect_events" in query for query in connection.executed)


class _JWKSResponse:
    headers = {"cache-control": "max-age=300"}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return {"keys": [{"kid": "known-key"}]}


class _JWKSClient:
    def __init__(self) -> None:
        self.get_calls = 0

    async def get(self, _url: str) -> _JWKSResponse:
        self.get_calls += 1
        return _JWKSResponse()


def _unverified_token(kid: str) -> str:
    raw = json.dumps({"alg": "RS256", "kid": kid}, separators=(",", ":")).encode()
    header = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    return f"{header}.e30.eA"


def test_unknown_kid_negative_cache_and_global_throttle_bound_jwks_fetches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [100.0]
    monkeypatch.setattr(oidc_module.time, "monotonic", lambda: clock[0])
    client = _JWKSClient()
    verifier = OIDCVerifier(
        OIDCSettings(
            issuer="https://id.example/realms/acme",
            audience="xa-guard-api",
            client_id="xa-guard-api",
            client_secret="secret",
        ),
        client=client,
    )
    verifier.discovery = {"jwks_uri": "https://id.example/jwks"}
    verifier.jwks = {"keys": [{"kid": "known-key"}]}
    verifier.jwks_fetched_at = clock[0]
    verifier.jwks_max_age = 300

    async def exercise() -> None:
        with pytest.raises(OIDCError):
            await verifier.verify(_unverified_token("attacker-key-1"))
        with pytest.raises(OIDCError):
            await verifier.verify(_unverified_token("attacker-key-1"))
        with pytest.raises(OIDCError):
            await verifier.verify(_unverified_token("attacker-key-2"))
        assert client.get_calls == 1
        clock[0] += 6
        with pytest.raises(OIDCError):
            await verifier.verify(_unverified_token("attacker-key-3"))

    asyncio.run(exercise())
    assert client.get_calls == 2
