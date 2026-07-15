"""Environment-driven assembly for API, migration, and worker processes."""

from __future__ import annotations

import base64
import binascii
import os
from dataclasses import dataclass
from pathlib import Path

from xa_guard.config import XAGuardConfig
from xa_guard.control.business import BusinessClient
from xa_guard.control.audit import PostgresGate6Audit
from xa_guard.control.ceiling import GovernanceCeiling
from xa_guard.control.contracts import ContractRegistry
from xa_guard.control.crypto import CryptoError, InternalAuthorization, Keyring
from xa_guard.control.key_provider import (
    HttpKeyProvider,
    KeyProvider,
    KeyProviderError,
    LocalKeyProvider,
)
from xa_guard.control.oidc import OIDCSettings, OIDCVerifier
from xa_guard.control.service import ControlService
from xa_guard.control.store import AsyncEffectStore
from xa_guard.server import build_pipeline


@dataclass
class ControlRuntime:
    store: AsyncEffectStore
    business: BusinessClient
    verifier: OIDCVerifier
    service: ControlService
    key_provider: KeyProvider | None = None

    async def start(self, *, oidc: bool = True, migrate: bool = False) -> None:
        try:
            if self.key_provider is not None:
                await self.key_provider.start()
                if not await self.key_provider.ready():
                    raise KeyProviderError("key provider is not ready")
            await self.store.connect()
            if migrate:
                await self.store.migrate()
            await self.business.start()
            if oidc:
                await self.verifier.start()
        except Exception:
            try:
                await self.close()
            except Exception:
                pass
            raise

    async def close(self) -> None:
        first_error: Exception | None = None
        callbacks = [self.verifier.close, self.business.close, self.store.close]
        if self.key_provider is not None:
            callbacks.append(self.key_provider.close)
        for callback in callbacks:
            try:
                await callback()
            except Exception as exc:  # lifecycle teardown must attempt every resource
                if first_error is None:
                    first_error = exc
        if first_error is not None:
            raise first_error


def _secret(name: str) -> str:
    path = os.getenv(name + "_FILE", "")
    if path:
        return Path(path).read_text(encoding="utf-8").strip()
    value = os.getenv(name, "")
    if not value:
        raise RuntimeError(f"required secret is absent: {name} or {name}_FILE")
    return value


def _decode_secret(name: str) -> bytes:
    value = _secret(name)
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        try:
            raw = bytes.fromhex(value)
        except ValueError as exc:
            raise CryptoError(f"{name} must be base64 or hex") from exc
    if len(raw) < 32:
        raise CryptoError(f"{name} must contain at least 32 bytes")
    return raw


def build_key_provider() -> KeyProvider:
    provider_type = os.getenv("XA_GUARD_KEY_PROVIDER", "local").strip().lower()
    if provider_type == "local":
        return LocalKeyProvider(Keyring.from_json(_secret("XA_GUARD_KEK_KEYRING")))
    if provider_type == "http":
        base_url = os.getenv("XA_GUARD_KEY_PROVIDER_URL", "").strip()
        if not base_url:
            raise KeyProviderError("XA_GUARD_KEY_PROVIDER_URL is required for HTTP key provider")
        deployment_profile = os.getenv(
            "XA_GUARD_DEPLOYMENT_PROFILE", "development"
        ).strip().lower()
        reference_http_hosts = ()
        if deployment_profile != "production":
            reference_http_hosts = tuple(
                host.strip()
                for host in os.getenv(
                    "XA_GUARD_KEY_PROVIDER_REFERENCE_HTTP_HOSTS",
                    "kms,key-provider,reference-kms,localhost,127.0.0.1",
                ).split(",")
                if host.strip()
            )
        return HttpKeyProvider(
            base_url,
            _secret("XA_GUARD_KEY_PROVIDER_AUTH_TOKEN"),
            ca_file=os.getenv("XA_GUARD_KEY_PROVIDER_CA_FILE", "").strip(),
            timeout_seconds=float(os.getenv("XA_GUARD_KEY_PROVIDER_TIMEOUT_SECONDS", "5")),
            reference_http_hosts=reference_http_hosts,
        )
    raise KeyProviderError("XA_GUARD_KEY_PROVIDER must be local or http")


def build_migration_store() -> AsyncEffectStore:
    """Build a DB-only store; migrations must not depend on KMS or other services."""

    return AsyncEffectStore(_secret("XA_GUARD_DATABASE_URL"))


def build_keyed_store() -> tuple[AsyncEffectStore, KeyProvider]:
    """Build the DB + key-provider subset used by online rewrap tooling."""

    key_provider = build_key_provider()
    return AsyncEffectStore(_secret("XA_GUARD_DATABASE_URL"), key_provider), key_provider


def build_runtime() -> ControlRuntime:
    store, key_provider = build_keyed_store()
    business = BusinessClient(os.environ["REFERENCE_BUSINESS_API_URL"], _secret("REFERENCE_BUSINESS_API_KEY"))
    deployment_profile = os.getenv("XA_GUARD_DEPLOYMENT_PROFILE", "development").strip().lower()
    reference_http_hosts = ()
    if deployment_profile != "production":
        reference_http_hosts = tuple(
            host.strip()
            for host in os.getenv(
                "XA_GUARD_OIDC_REFERENCE_HTTP_HOSTS",
                "keycloak,127.0.0.1,localhost",
            ).split(",")
            if host.strip()
        )
    verifier = OIDCVerifier(
        OIDCSettings(
            issuer=os.environ["XA_GUARD_OIDC_ISSUER"],
            audience=os.getenv("XA_GUARD_OIDC_AUDIENCE", "xa-guard-api"),
            client_id=os.getenv("XA_GUARD_OIDC_INTROSPECTION_CLIENT_ID", "xa-guard-api"),
            client_secret=_secret("XA_GUARD_OIDC_INTROSPECTION_CLIENT_SECRET"),
            algorithms=tuple(os.getenv("XA_GUARD_OIDC_ALGORITHMS", "RS256").split(",")),
            stale_grace_seconds=int(
                os.getenv("XA_GUARD_JWKS_STALE_GRACE_SECONDS", "900")
            ),
            backchannel_base_url=os.getenv("XA_GUARD_OIDC_BACKCHANNEL_BASE_URL", ""),
            role_clients=tuple(
                value.strip()
                for value in os.getenv(
                    "XA_GUARD_OIDC_ROLE_CLIENTS", "xa-guard-api,general-office-agent"
                ).split(",")
                if value.strip()
            ),
            reference_http_hosts=reference_http_hosts,
            ca_file=os.getenv("XA_GUARD_OIDC_CA_FILE", "").strip(),
        )
    )
    config_path = os.getenv("XA_GUARD_REFERENCE_CONFIG", "configs/xa-guard.reference.yaml")
    config = XAGuardConfig.from_yaml(config_path)
    pipeline = build_pipeline(
        config,
        gate6=PostgresGate6Audit(config.gate("gate6"), store),
    )
    contracts = ContractRegistry(
        os.getenv("XA_GUARD_EFFECT_CONTRACTS", "policies/baseline/tool_effects.yaml"),
        os.getenv("XA_GUARD_TOOL_CAPABILITIES", "policies/baseline/gate4_capabilities.yaml"),
    )
    ceiling = GovernanceCeiling(
        os.getenv("XA_GUARD_GOVERNANCE_CEILING", "configs/governance.enterprise-static.yaml")
    )
    signer = InternalAuthorization(_decode_secret("XA_GUARD_INTERNAL_AUTH_KEY"))
    service = ControlService(
        store=store,
        business=business,
        pipeline=pipeline,
        contracts=contracts,
        ceiling=ceiling,
        internal_authorization=signer,
    )
    return ControlRuntime(store, business, verifier, service, key_provider)
