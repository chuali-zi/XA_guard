"""OIDC discovery, JWKS lifecycle, Keycloak/external-STS claim mapping, and introspection."""

from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import jwt

from xa_guard.control.models import Principal


class OIDCError(RuntimeError):
    code = "invalid_token"


@dataclass(frozen=True)
class OIDCSettings:
    issuer: str
    audience: str
    client_id: str
    client_secret: str
    algorithms: tuple[str, ...] = ("RS256",)
    stale_grace_seconds: int = 900
    timeout_seconds: float = 5.0
    backchannel_base_url: str = ""
    role_clients: tuple[str, ...] = ()
    unknown_kid_ttl_seconds: int = 30
    unknown_kid_refresh_interval_seconds: int = 5
    reference_http_hosts: tuple[str, ...] = ("keycloak", "127.0.0.1", "localhost")
    ca_file: str = ""


class OIDCVerifier:
    """Startup discovery is mandatory; sensitive paths always introspect."""

    def __init__(self, settings: OIDCSettings, client: Any | None = None) -> None:
        self.settings = settings
        self.client = client
        self.discovery: dict[str, Any] = {}
        self.jwks: dict[str, Any] = {}
        self.jwks_fetched_at = 0.0
        self.jwks_max_age = 0
        self.last_refresh_ok = False
        self._jwks_lock = asyncio.Lock()
        self._unknown_kids: dict[str, float] = {}
        self._last_unknown_kid_refresh = float("-inf")

    async def start(self) -> None:
        if self.client is None:
            import httpx

            self.client = httpx.AsyncClient(
                timeout=self.settings.timeout_seconds,
                verify=self.settings.ca_file or True,
            )
        url = self._backchannel(
            self.settings.issuer.rstrip("/") + "/.well-known/openid-configuration"
        )
        if not self._safe_endpoint(url):
            raise OIDCError("OIDC discovery URL is not permitted")
        response = await self.client.get(url)
        response.raise_for_status()
        self.discovery = response.json()
        if self.discovery.get("issuer") != self.settings.issuer:
            raise OIDCError("OIDC discovery issuer mismatch")
        for key in ("jwks_uri", "introspection_endpoint"):
            endpoint = self._backchannel(str(self.discovery.get(key) or ""))
            if not self._safe_endpoint(endpoint):
                raise OIDCError(f"OIDC discovery is missing a safe {key}")
        await self._refresh_jwks()

    async def close(self) -> None:
        if self.client is not None:
            await self.client.aclose()

    async def verify(self, token: str, *, sensitive: bool = False) -> Principal:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise OIDCError("malformed bearer token") from exc
        algorithm = str(header.get("alg") or "")
        kid = str(header.get("kid") or "")
        if algorithm not in self.settings.algorithms or not kid or len(kid) > 256:
            raise OIDCError("token algorithm or kid is not allowed")
        key = self._find_key(kid)
        now = time.monotonic()
        expired = now > self.jwks_fetched_at + self.jwks_max_age
        if key is None:
            try:
                key = await self._refresh_for_unknown_kid(kid)
            except Exception as exc:
                raise OIDCError("JWKS refresh failed for unknown token kid") from exc
            if key is None:
                raise OIDCError("token kid is unknown after forced JWKS refresh")
        elif expired:
            try:
                await self._refresh_jwks()
                key = self._find_key(kid)
                if key is None:
                    raise OIDCError("token kid is no longer present after JWKS refresh")
            except Exception as exc:
                stale_age = now - (self.jwks_fetched_at + self.jwks_max_age)
                if sensitive or stale_age > self.settings.stale_grace_seconds:
                    raise OIDCError("JWKS refresh failed outside permitted grace") from exc
        try:
            claims = jwt.decode(
                token,
                jwt.PyJWK.from_dict(key).key,
                algorithms=list(self.settings.algorithms),
                audience=self.settings.audience,
                issuer=self.settings.issuer,
                options={"require": ["exp", "iat", "sub", "iss"]},
                leeway=30,
            )
        except jwt.PyJWTError as exc:
            raise OIDCError("token signature or claims are invalid") from exc
        if sensitive:
            await self._introspect(token)
        return self._principal(claims, token)

    async def _refresh_jwks(self) -> None:
        async with self._jwks_lock:
            await self._fetch_jwks()

    async def _fetch_jwks(self) -> None:
        self.last_refresh_ok = False
        try:
            response = await self.client.get(self._backchannel(self.discovery["jwks_uri"]))
            response.raise_for_status()
            value = response.json()
            if not isinstance(value.get("keys"), list) or not value["keys"]:
                raise OIDCError("JWKS contains no keys")
            self.jwks = value
            self.jwks_fetched_at = time.monotonic()
            self.jwks_max_age = self._max_age(response.headers.get("cache-control", ""))
            self.last_refresh_ok = True
        except Exception:
            self.last_refresh_ok = False
            raise

    async def _refresh_for_unknown_kid(self, kid: str) -> dict[str, Any] | None:
        """Refresh at most once per interval and negatively cache unknown keys.

        The lock collapses concurrent misses.  A rotated key can still be picked
        up on the first request after the short throttle interval, while a flood
        of random ``kid`` values cannot force one outbound request per token.
        """

        async with self._jwks_lock:
            key = self._find_key(kid)
            if key is not None:
                return key
            now = time.monotonic()
            self._unknown_kids = {
                value: expires_at
                for value, expires_at in self._unknown_kids.items()
                if expires_at > now
            }
            if self._unknown_kids.get(kid, 0.0) > now:
                return None
            interval = max(1, self.settings.unknown_kid_refresh_interval_seconds)
            if now - self._last_unknown_kid_refresh < interval:
                self._remember_unknown_kid(kid, now)
                return None
            self._last_unknown_kid_refresh = now
            try:
                await self._fetch_jwks()
            except Exception:
                self._remember_unknown_kid(kid, now)
                raise
            key = self._find_key(kid)
            if key is None:
                self._remember_unknown_kid(kid, time.monotonic())
            else:
                self._unknown_kids.pop(kid, None)
            return key

    def _remember_unknown_kid(self, kid: str, now: float) -> None:
        if len(self._unknown_kids) >= 256:
            oldest = min(self._unknown_kids, key=self._unknown_kids.__getitem__)
            self._unknown_kids.pop(oldest, None)
        ttl = max(1, min(self.settings.unknown_kid_ttl_seconds, 300))
        self._unknown_kids[kid] = now + ttl

    async def _introspect(self, token: str) -> None:
        try:
            response = await self.client.post(
                self._backchannel(self.discovery["introspection_endpoint"]),
                data={"token": token, "client_id": self.settings.client_id, "client_secret": self.settings.client_secret},
                headers={"accept": "application/json"},
            )
            response.raise_for_status()
            value = response.json()
        except Exception as exc:
            raise OIDCError("token introspection is unavailable") from exc
        if value.get("active") is not True:
            raise OIDCError("token is inactive")

    def _find_key(self, kid: str) -> dict[str, Any] | None:
        matches = [value for value in self.jwks.get("keys", []) if value.get("kid") == kid]
        return matches[0] if len(matches) == 1 else None

    def _backchannel(self, value: str) -> str:
        if not self.settings.backchannel_base_url:
            return value
        source = urlsplit(value)
        target = urlsplit(self.settings.backchannel_base_url)
        prefix = target.path.rstrip("/")
        return urlunsplit((target.scheme, target.netloc, prefix + source.path, source.query, ""))

    def _safe_endpoint(self, value: str) -> bool:
        parsed = urlsplit(value)
        if parsed.scheme == "https" and parsed.hostname:
            return True
        allowed = {host.strip().lower() for host in self.settings.reference_http_hosts if host.strip()}
        return bool(
            parsed.scheme == "http"
            and parsed.hostname
            and parsed.hostname.lower() in allowed
        )

    @staticmethod
    def _max_age(cache_control: str) -> int:
        for part in cache_control.split(","):
            name, _, raw = part.strip().partition("=")
            if name.lower() == "max-age" and raw.isdigit():
                return max(30, min(int(raw), 3600))
        return 300

    def _principal(self, claims: dict[str, Any], token: str) -> Principal:
        actor = claims.get("act") if isinstance(claims.get("act"), dict) else {}
        agent_id = str(actor.get("sub") or claims.get("azp") or "")
        subject = str(claims.get("sub") or "")
        username = str(claims.get("preferred_username") or subject)
        tenant_id = str(claims.get("tenant_id") or "")
        if not subject or not agent_id or not tenant_id:
            raise OIDCError("sub, tenant_id, and act.sub or azp are required")
        groups = self._strings(claims.get("groups"))
        realm_access = claims.get("realm_access") if isinstance(claims.get("realm_access"), dict) else {}
        roles: set[str] = set(self._strings(realm_access.get("roles")))
        resources = claims.get("resource_access") or {}
        if isinstance(resources, dict):
            allowed_clients = self.settings.role_clients or (self.settings.client_id,)
            for client_id, value in resources.items():
                if client_id not in allowed_clients:
                    continue
                if isinstance(value, dict):
                    roles.update(self._strings(value.get("roles")))
        scope = claims.get("scope") or ""
        scopes = tuple(str(scope).split()) if isinstance(scope, str) else self._strings(scope)
        return Principal(
            subject=subject,
            username=username,
            tenant_id=tenant_id,
            agent_id=agent_id,
            issuer=self.settings.issuer,
            token_id_hash=hashlib.sha256(token.encode()).hexdigest(),
            roles=tuple(sorted(roles)),
            groups=groups,
            scopes=scopes,
        )

    @staticmethod
    def _strings(value: Any) -> tuple[str, ...]:
        if isinstance(value, str):
            return (value,)
        if isinstance(value, (list, tuple, set)):
            return tuple(str(item) for item in value if str(item))
        return ()


async def bearer_principal(request: Any, *, sensitive: bool = False) -> Principal:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise OIDCError("Bearer token is required")
    principal = await request.app.state.verifier.verify(token, sensitive=sensitive)
    request.state.principal = principal
    return principal
