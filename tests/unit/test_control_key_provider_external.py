from __future__ import annotations

import asyncio
import base64
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from xa_guard.control.crypto import EncryptedEnvelope, Keyring, canonical_json
from xa_guard.control.key_provider import (
    HttpKeyProvider,
    KeyProviderError,
    LocalKeyProvider,
)
from xa_guard.control.runtime import ControlRuntime, build_key_provider, build_migration_store
from xa_guard.control.store import AsyncEffectStore
from xa_guard.reference.kms_api import create_app


class _Response:
    def __init__(self, value: dict[str, Any], status_code: int = 200) -> None:
        self.value = value
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError("upstream body contained super-secret-debug-data")

    def json(self) -> dict[str, Any]:
        return self.value


class _KMSClient:
    def __init__(self, keyring: Keyring) -> None:
        self.keyring = keyring
        self.headers: list[dict[str, str]] = []

    async def get(self, _url: str, *, headers: dict[str, str]) -> _Response:
        self.headers.append(headers)
        return _Response(
            {"status": "ready", "active_key_id": self.keyring.active_key_id}
        )

    async def post(
        self, url: str, *, json: dict[str, Any], headers: dict[str, str]
    ) -> _Response:
        self.headers.append(headers)
        if url.endswith("/v1/wrap"):
            key_id, wrapped = self.keyring.wrap_key(
                base64.b64decode(json["plaintext_key"])
            )
            return _Response(
                {
                    "key_id": key_id,
                    "wrapped_key": base64.b64encode(wrapped).decode(),
                }
            )
        if url.endswith("/v1/unwrap"):
            plaintext = self.keyring.unwrap_key(
                json["key_id"], base64.b64decode(json["wrapped_key"])
            )
            return _Response(
                {"plaintext_key": base64.b64encode(plaintext).decode()}
            )
        key_id, wrapped = self.keyring.rewrap_key(
            json["key_id"], base64.b64decode(json["wrapped_key"])
        )
        return _Response(
            {"key_id": key_id, "wrapped_key": base64.b64encode(wrapped).decode()}
        )


def test_local_provider_preserves_keyring_roundtrip_and_rewrap() -> None:
    old = LocalKeyProvider(Keyring({"v1": b"a" * 32}, "v1"))
    rotated = LocalKeyProvider(
        Keyring({"v1": b"a" * 32, "v2": b"b" * 32}, "v2")
    )

    async def exercise() -> None:
        envelope = await old.encrypt(b"recovery", b"aad")
        updated = await rotated.rewrap(envelope)
        assert updated.key_id == "v2"
        assert updated.ciphertext == envelope.ciphertext
        assert await rotated.decrypt(updated, b"aad") == b"recovery"

    asyncio.run(exercise())


def test_http_provider_keeps_kek_remote_and_uses_bearer_for_every_operation() -> None:
    kms_ring = Keyring({"v1": b"a" * 32, "v2": b"b" * 32}, "v2")
    client = _KMSClient(kms_ring)
    provider = HttpKeyProvider(
        "https://kms.example",
        "provider-token",
        client=client,
    )
    old_envelope = Keyring({"v1": b"a" * 32}, "v1").encrypt(
        b"old recovery", b"old-aad"
    )

    async def exercise() -> None:
        await provider.start()
        assert await provider.ready() is True
        envelope = await provider.encrypt(b"new recovery", b"new-aad")
        assert await provider.decrypt(envelope, b"new-aad") == b"new recovery"
        updated = await provider.rewrap(old_envelope)
        assert updated.key_id == "v2"
        assert await provider.decrypt(updated, b"old-aad") == b"old recovery"

    asyncio.run(exercise())
    assert client.headers
    assert all(
        headers["authorization"] == "Bearer provider-token"
        for headers in client.headers
    )
    assert not hasattr(provider, "keyring")


class _FailingClient:
    async def post(self, *_args: Any, **_kwargs: Any) -> _Response:
        return _Response({}, status_code=500)


def test_http_provider_errors_are_sanitized_and_fail_closed() -> None:
    provider = HttpKeyProvider(
        "https://kms.example", "provider-token", client=_FailingClient()
    )

    async def exercise() -> None:
        with pytest.raises(KeyProviderError) as caught:
            await provider.encrypt(b"recovery", b"aad")
        assert str(caught.value) == "key provider operation failed"
        assert "super-secret" not in str(caught.value)

    asyncio.run(exercise())


def test_runtime_http_mode_does_not_require_or_read_local_kek(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XA_GUARD_KEY_PROVIDER", "http")
    monkeypatch.setenv("XA_GUARD_KEY_PROVIDER_URL", "https://kms.example")
    monkeypatch.setenv("XA_GUARD_KEY_PROVIDER_AUTH_TOKEN", "provider-token")
    monkeypatch.setenv("XA_GUARD_DEPLOYMENT_PROFILE", "production")
    monkeypatch.delenv("XA_GUARD_KEK_KEYRING", raising=False)
    monkeypatch.delenv("XA_GUARD_KEK_KEYRING_FILE", raising=False)

    assert isinstance(build_key_provider(), HttpKeyProvider)


def test_runtime_production_rejects_plain_http_key_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XA_GUARD_KEY_PROVIDER", "http")
    monkeypatch.setenv("XA_GUARD_KEY_PROVIDER_URL", "http://reference-kms:8083")
    monkeypatch.setenv("XA_GUARD_KEY_PROVIDER_AUTH_TOKEN", "provider-token")
    monkeypatch.setenv("XA_GUARD_DEPLOYMENT_PROFILE", "production")

    with pytest.raises(KeyProviderError):
        build_key_provider()


def test_migration_store_requires_only_database_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XA_GUARD_DATABASE_URL", "postgresql://db-only")
    for name in (
        "XA_GUARD_KEK_KEYRING",
        "XA_GUARD_KEK_KEYRING_FILE",
        "XA_GUARD_KEY_PROVIDER_AUTH_TOKEN",
        "XA_GUARD_KEY_PROVIDER_AUTH_TOKEN_FILE",
        "XA_GUARD_OIDC_INTROSPECTION_CLIENT_SECRET",
        "REFERENCE_BUSINESS_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    store = build_migration_store()
    assert store.dsn == "postgresql://db-only"
    assert store.key_provider is None


class _LifecycleStore:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    async def connect(self) -> None:
        self.calls.append("store.connect")

    async def migrate(self) -> None:
        self.calls.append("store.migrate")

    async def close(self) -> None:
        self.calls.append("store.close")


class _LifecycleDependency:
    def __init__(self, name: str, calls: list[str], *, ready: bool = True) -> None:
        self.name = name
        self.calls = calls
        self.ready_value = ready

    async def start(self) -> None:
        self.calls.append(f"{self.name}.start")

    async def ready(self) -> bool:
        self.calls.append(f"{self.name}.ready")
        return self.ready_value

    async def close(self) -> None:
        self.calls.append(f"{self.name}.close")


def test_control_runtime_starts_health_checks_and_closes_key_provider() -> None:
    calls: list[str] = []
    provider = _LifecycleDependency("provider", calls)
    runtime = ControlRuntime(
        store=_LifecycleStore(calls),  # type: ignore[arg-type]
        business=_LifecycleDependency("business", calls),  # type: ignore[arg-type]
        verifier=_LifecycleDependency("oidc", calls),  # type: ignore[arg-type]
        service=object(),  # type: ignore[arg-type]
        key_provider=provider,  # type: ignore[arg-type]
    )

    async def exercise() -> None:
        await runtime.start(oidc=True, migrate=True)
        await runtime.close()

    asyncio.run(exercise())
    assert calls[:4] == [
        "provider.start",
        "provider.ready",
        "store.connect",
        "store.migrate",
    ]
    assert calls[-1] == "provider.close"


def test_reference_kms_wrap_unwrap_rewrap_and_authentication() -> None:
    ring = Keyring({"v1": b"a" * 32, "v2": b"b" * 32}, "v2")
    app = create_app(keyring=ring, auth_token="kms-token")
    headers = {"Authorization": "Bearer kms-token"}
    plaintext = b"d" * 32
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/readyz").status_code == 401
        ready = client.get("/readyz", headers=headers)
        assert ready.json() == {"status": "ready", "active_key_id": "v2"}
        wrapped = client.post(
            "/v1/wrap",
            headers=headers,
            json={"plaintext_key": base64.b64encode(plaintext).decode()},
        )
        assert wrapped.status_code == 200
        unwrapped = client.post(
            "/v1/unwrap", headers=headers, json=wrapped.json()
        )
        assert base64.b64decode(unwrapped.json()["plaintext_key"]) == plaintext

        old_id, old_wrapped = Keyring({"v1": b"a" * 32}, "v1").wrap_key(
            plaintext
        )
        rotated = client.post(
            "/v1/rewrap",
            headers=headers,
            json={
                "key_id": old_id,
                "wrapped_key": base64.b64encode(old_wrapped).decode(),
            },
        )
        assert rotated.status_code == 200
        assert rotated.json()["key_id"] == "v2"


class _AsyncProvider:
    active_key_id = "v1"

    def __init__(self) -> None:
        self.encrypt_awaited = False

    async def encrypt(self, plaintext: bytes, aad: bytes) -> EncryptedEnvelope:
        await asyncio.sleep(0)
        self.encrypt_awaited = True
        return Keyring({"v1": b"a" * 32}, "v1").encrypt(plaintext, aad)

    async def decrypt(self, envelope: EncryptedEnvelope, aad: bytes) -> bytes:
        return Keyring({"v1": b"a" * 32}, "v1").decrypt(envelope, aad)

    async def rewrap(self, envelope: EncryptedEnvelope) -> EncryptedEnvelope:
        return envelope

    async def start(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def ready(self) -> bool:
        return True


class _StoreTransaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *_args: Any) -> None:
        return None


class _StoreConnection:
    def transaction(self) -> _StoreTransaction:
        return _StoreTransaction()

    async def execute(self, *_args: Any) -> None:
        return None

    async def fetchval(self, query: str, *_args: Any) -> int | str:
        return "" if "SELECT record_hash" in query else 1


class _StoreAcquire:
    def __init__(self, connection: _StoreConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> _StoreConnection:
        return self.connection

    async def __aexit__(self, *_args: Any) -> None:
        return None


class _StorePool:
    def __init__(self) -> None:
        self.connection = _StoreConnection()

    async def fetchrow(self, *_args: Any) -> dict[str, str]:
        return {
            "tenant_id": "acme",
            "tool_name": "business_submit_ticket",
            "reversibility": "compensatable",
            "status": "prepared",
        }

    def acquire(self) -> _StoreAcquire:
        return _StoreAcquire(self.connection)


def test_store_awaits_async_provider_before_persisting_ciphertext() -> None:
    provider = _AsyncProvider()
    store = AsyncEffectStore("postgresql://unused", provider)
    store.pool = _StorePool()
    principal = type("Principal", (), {"tenant_id": "acme", "subject": "alice"})()

    asyncio.run(
        store.complete_effect(
            "eff-1",
            principal,  # type: ignore[arg-type]
            {"ticket_id": "T-1"},
            {"ok": True},
            "T-1",
        )
    )
    assert provider.encrypt_awaited is True


def test_reference_kms_keyring_environment_is_distinct_from_application_contract() -> None:
    source = Path("src/xa_guard/reference/kms_api.py").read_text(encoding="utf-8")
    assert "REFERENCE_KMS_KEK_KEYRING" in source
    assert "XA_GUARD_KEK_KEYRING" not in source
    assert canonical_json({"b": 2, "a": 1}) == b'{"a":1,"b":2}'
