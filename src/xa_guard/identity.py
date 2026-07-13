"""Cryptographically verified human -> agent identity binding for MCP calls."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jwt
import anyio
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken

from xa_guard.config import IdentityConfig, IdentityIssuerConfig


class IdentityError(ValueError):
    pass


log = logging.getLogger("xa_guard.identity")


@dataclass(frozen=True)
class VerifiedIdentity:
    human_principal: str
    agent_id: str
    tenant_id: str
    issuer: str
    scopes: tuple[str, ...]
    tools: tuple[str, ...]
    data_domains: tuple[str, ...]
    permissions: tuple[str, ...]
    kid: str
    jti_sha256: str


class JWTIdentityVerifier:
    """MCP TokenVerifier using an exact issuer allowlist and signed JWKS keys."""

    def __init__(self, cfg: IdentityConfig) -> None:
        self.cfg = cfg
        self._issuers = {item.issuer: item for item in cfg.issuers}
        self._local_jwks: dict[str, dict[str, Any]] = {}
        self._remote_clients: dict[str, jwt.PyJWKClient] = {}
        for item in cfg.issuers:
            if bool(item.jwks_file) == bool(item.jwks_uri):
                raise IdentityError(f"issuer {item.issuer} must configure exactly one of jwks_file/jwks_uri")
            if item.jwks_file:
                payload = json.loads(Path(item.jwks_file).read_text(encoding="utf-8"))
                self._local_jwks[item.issuer] = payload
            else:
                self._remote_clients[item.issuer] = jwt.PyJWKClient(item.jwks_uri, cache_jwk_set=True)

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            return await anyio.to_thread.run_sync(self.verify, token)
        except (IdentityError, jwt.PyJWTError, OSError, ValueError, KeyError):
            return None

    def verify(self, token: str) -> AccessToken:
        header = jwt.get_unverified_header(token)
        unverified = jwt.decode(token, options={"verify_signature": False})
        issuer_name = str(unverified.get("iss") or "")
        issuer = self._issuers.get(issuer_name)
        if issuer is None:
            raise IdentityError("issuer is not allowlisted")
        algorithm = str(header.get("alg") or "")
        if algorithm not in issuer.algorithms or algorithm.lower() == "none":
            raise IdentityError("JWT algorithm is not allowlisted")
        key = self._signing_key(token, issuer, str(header.get("kid") or ""))
        claims = jwt.decode(
            token,
            key=key,
            algorithms=issuer.algorithms,
            audience=issuer.audiences or None,
            issuer=issuer.issuer,
            leeway=self.cfg.clock_skew_seconds,
            options={"require": ["exp", "iat", "sub", "iss", "jti"]},
        )
        actor = claims.get("act") if isinstance(claims.get("act"), dict) else {}
        human = str(claims.get("sub") or "")
        agent = str(actor.get("sub") or "")
        tenant = str(claims.get("tenant_id") or "")
        if not human or not agent or not tenant:
            raise IdentityError("sub, act.sub and tenant_id are required")
        issued_at, expires_at = int(claims["iat"]), int(claims["exp"])
        if expires_at - issued_at > self.cfg.max_token_ttl_seconds:
            raise IdentityError("token lifetime exceeds configured maximum")
        if issued_at > int(time.time()) + self.cfg.clock_skew_seconds:
            raise IdentityError("token issued in the future")
        scopes = _strings(claims.get("scope") or claims.get("scopes"), split=True)
        safe_claims = {
            "iss": issuer.issuer,
            "act": {"sub": agent},
            "tenant_id": tenant,
            "tools": list(_strings(claims.get("tools"))),
            "data_domains": list(_strings(claims.get("data_domains"))),
            "permissions": list(_strings(claims.get("permissions"))),
            "kid": str(header.get("kid") or ""),
            "jti_sha256": hashlib.sha256(str(claims.get("jti") or "").encode()).hexdigest(),
        }
        return AccessToken(
            token=hashlib.sha256(token.encode()).hexdigest(),
            client_id=agent,
            scopes=list(scopes),
            expires_at=expires_at,
            resource=str((issuer.audiences or [""])[0]),
            subject=human,
            claims=safe_claims,
        )

    def _signing_key(self, token: str, issuer: IdentityIssuerConfig, kid: str) -> Any:
        if issuer.jwks_file:
            keys = self._local_jwks[issuer.issuer].get("keys", [])
            matches = [item for item in keys if str(item.get("kid") or "") == kid]
            if len(matches) != 1:
                raise IdentityError("JWT kid is missing or ambiguous")
            return jwt.PyJWK.from_dict(matches[0]).key
        return self._remote_clients[issuer.issuer].get_signing_key_from_jwt(token).key


def _strings(value: Any, *, split: bool = False) -> tuple[str, ...]:
    if split and isinstance(value, str):
        value = value.split()
    if not isinstance(value, (list, tuple, set)):
        return ()
    return tuple(str(item) for item in value if str(item))


def identity_from_access_token(token: AccessToken) -> VerifiedIdentity:
    claims = token.claims or {}
    actor = claims.get("act") if isinstance(claims.get("act"), dict) else {}
    return VerifiedIdentity(
        human_principal=str(token.subject or ""),
        agent_id=str(actor.get("sub") or token.client_id or ""),
        tenant_id=str(claims.get("tenant_id") or ""),
        issuer=str(claims.get("iss") or ""),
        scopes=tuple(token.scopes or []),
        tools=_strings(claims.get("tools")),
        data_domains=_strings(claims.get("data_domains")),
        permissions=_strings(claims.get("permissions")),
        kid=str(claims.get("kid") or ""),
        jti_sha256=str(claims.get("jti_sha256") or ""),
    )


def binding_error(identity: VerifiedIdentity, tool_name: str, envelope: dict[str, Any]) -> str:
    if not envelope:
        return "governance envelope is required"
    expected = {
        "human_principal": identity.human_principal,
        "agent_id": identity.agent_id,
        "tenant_id": identity.tenant_id,
    }
    for key, expected_value in expected.items():
        if str(envelope.get(key) or "") != expected_value:
            return f"{key} conflicts with verified bearer identity"
    if tool_name not in identity.tools:
        return f"tool {tool_name} is outside bearer scope"
    domain = str(envelope.get("data_domain") or "")
    if domain and domain not in identity.data_domains:
        return f"data domain {domain} is outside bearer scope"
    return ""


class IdentityBindingMiddleware:
    """Reject an MCP tools/call whose body conflicts with authenticated claims."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or scope.get("method") != "POST":
            await self.app(scope, receive, send)
            return
        chunks: list[bytes] = []
        while True:
            message = await receive()
            if message.get("type") == "http.disconnect":
                return
            if message.get("type") == "http.request":
                chunks.append(message.get("body", b""))
                if not message.get("more_body", False):
                    break
        body = b"".join(chunks)
        replayed = False

        async def replay() -> dict[str, Any]:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        try:
            payload = json.loads(body or b"{}")
        except ValueError:
            await self.app(scope, replay, send)
            return
        if payload.get("method") != "tools/call":
            await self.app(scope, replay, send)
            return
        user = scope.get("user")
        if not isinstance(user, AuthenticatedUser):
            log.warning("identity binding denied: verified bearer identity absent")
            await _json_error(send, 401, "invalid_token", "verified bearer identity is required")
            return
        params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
        arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        envelope = arguments.get("_xa_guard") if isinstance(arguments.get("_xa_guard"), dict) else {}
        error = binding_error(identity_from_access_token(user.access_token), str(params.get("name") or ""), envelope)
        if error:
            log.warning("identity binding denied: %s tool=%s", error, str(params.get("name") or ""))
            await _json_error(send, 403, "identity_context_mismatch", error)
            return
        await self.app(scope, replay, send)


async def _json_error(send: Any, status: int, error: str, description: str) -> None:
    body = json.dumps({"error": error, "error_description": description}).encode()
    await send({"type": "http.response.start", "status": status, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})
