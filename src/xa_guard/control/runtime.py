"""Environment-driven assembly for API, migration, and worker processes."""

from __future__ import annotations

import base64
import binascii
import os
from dataclasses import dataclass
from pathlib import Path

from xa_guard.config import XAGuardConfig
from xa_guard.control.business import BusinessClient
from xa_guard.control.ceiling import GovernanceCeiling
from xa_guard.control.contracts import ContractRegistry
from xa_guard.control.crypto import CryptoError, InternalAuthorization, Keyring
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

    async def start(self, *, oidc: bool = True, migrate: bool = False) -> None:
        await self.store.connect()
        if migrate:
            await self.store.migrate()
        await self.business.start()
        if oidc:
            await self.verifier.start()

    async def close(self) -> None:
        await self.verifier.close()
        await self.business.close()
        await self.store.close()


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


def build_runtime() -> ControlRuntime:
    keyring = Keyring.from_json(_secret("XA_GUARD_KEK_KEYRING"))
    store = AsyncEffectStore(_secret("XA_GUARD_DATABASE_URL"), keyring)
    business = BusinessClient(os.environ["REFERENCE_BUSINESS_API_URL"], _secret("REFERENCE_BUSINESS_API_KEY"))
    verifier = OIDCVerifier(
        OIDCSettings(
            issuer=os.environ["XA_GUARD_OIDC_ISSUER"],
            audience=os.getenv("XA_GUARD_OIDC_AUDIENCE", "xa-guard-api"),
            client_id=os.getenv("XA_GUARD_OIDC_INTROSPECTION_CLIENT_ID", "xa-guard-api"),
            client_secret=_secret("XA_GUARD_OIDC_INTROSPECTION_CLIENT_SECRET"),
            algorithms=tuple(os.getenv("XA_GUARD_OIDC_ALGORITHMS", "RS256").split(",")),
            backchannel_base_url=os.getenv("XA_GUARD_OIDC_BACKCHANNEL_BASE_URL", ""),
            role_clients=tuple(
                value.strip()
                for value in os.getenv(
                    "XA_GUARD_OIDC_ROLE_CLIENTS", "xa-guard-api,general-office-agent"
                ).split(",")
                if value.strip()
            ),
        )
    )
    config_path = os.getenv("XA_GUARD_REFERENCE_CONFIG", "configs/xa-guard.reference.yaml")
    pipeline = build_pipeline(XAGuardConfig.from_yaml(config_path))
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
    return ControlRuntime(store, business, verifier, service)
