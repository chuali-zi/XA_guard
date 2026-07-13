from __future__ import annotations

import json
import asyncio
import time

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from xa_guard.config import IdentityConfig, IdentityIssuerConfig
from xa_guard.identity import JWTIdentityVerifier, binding_error, identity_from_access_token
from xa_guard.identity import IdentityBindingMiddleware
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser


def _authority(tmp_path):
    private = Ed25519PrivateKey.generate()
    public = private.public_key()
    jwk = json.loads(jwt.algorithms.OKPAlgorithm.to_jwk(public))
    jwk.update({"kid": "current", "use": "sig", "alg": "EdDSA"})
    path = tmp_path / "jwks.json"
    path.write_text(json.dumps({"keys": [jwk]}), encoding="utf-8")
    cfg = IdentityConfig(
        enabled=True,
        required=True,
        issuers=[IdentityIssuerConfig("https://issuer.test", ["https://guard.test/mcp"], str(path), algorithms=["EdDSA"])],
    )
    return private, JWTIdentityVerifier(cfg)


def _token(private, **overrides):
    now = int(time.time())
    claims = {
        "iss": "https://issuer.test", "aud": "https://guard.test/mcp", "sub": "alice",
        "act": {"sub": "office-agent"}, "tenant_id": "tenant-a", "iat": now, "exp": now + 120,
        "jti": "secret-jti", "scope": "xa.invoke", "tools": ["business_submit_ticket"],
        "data_domains": ["engineering_docs"], "permissions": ["undo.request"],
    }
    claims.update(overrides)
    return jwt.encode(claims, private, algorithm="EdDSA", headers={"kid": "current"})


def test_verified_identity_binds_human_agent_tenant_and_never_keeps_raw_token(tmp_path):
    private, verifier = _authority(tmp_path)
    raw = _token(private)
    access = verifier.verify(raw)
    identity = identity_from_access_token(access)
    assert (identity.human_principal, identity.agent_id, identity.tenant_id) == ("alice", "office-agent", "tenant-a")
    assert access.token == __import__("hashlib").sha256(raw.encode()).hexdigest()
    assert raw not in json.dumps(access.claims)
    assert binding_error(identity, "business_submit_ticket", {"human_principal": "mallory", "agent_id": "office-agent", "tenant_id": "tenant-a"})


def test_http_binding_middleware_rejects_body_identity_conflict_before_inner_app(tmp_path):
    private, verifier = _authority(tmp_path)
    access = verifier.verify(_token(private))
    called = False
    messages = []

    async def inner(_scope, _receive, _send):
        nonlocal called
        called = True

    payload = json.dumps({"method": "tools/call", "params": {"name": "business_submit_ticket", "arguments": {"_xa_guard": {"human_principal": "mallory", "agent_id": "office-agent", "tenant_id": "tenant-a"}}}}).encode()
    delivered = False
    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": payload, "more_body": False}
        return {"type": "http.disconnect"}
    async def send(message):
        messages.append(message)
    scope = {"type": "http", "method": "POST", "user": AuthenticatedUser(access)}
    asyncio.run(IdentityBindingMiddleware(inner)(scope, receive, send))
    assert called is False
    assert messages[0]["status"] == 403


def test_bad_signature_wrong_audience_and_excessive_ttl_fail_closed(tmp_path):
    private, verifier = _authority(tmp_path)
    other = Ed25519PrivateKey.generate()
    assert asyncio.run(verifier.verify_token(_token(other))) is None
    assert asyncio.run(verifier.verify_token(_token(private, aud="wrong"))) is None
    now = int(time.time())
    assert asyncio.run(verifier.verify_token(_token(private, iat=now, exp=now + 1000))) is None
