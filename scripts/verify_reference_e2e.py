"""Run the real local Keycloak PKCE + two-person Undo reference flow.

This verifier deliberately uses Authorization Code + PKCE and the Console BFF.
It never prints, persists, or returns an access token.  It is suitable for the
generated local reference realm only; browser visual QA remains a separate
manual acceptance item.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import secrets
import time
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CREDENTIALS = ROOT / ".runtime" / "reference" / "credentials.json"


class VerificationError(RuntimeError):
    """A safe, credential-free verification failure."""


class _LoginFormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.action = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "form" and values.get("id") == "kc-form-login":
            self.action = str(values.get("action") or "")


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _expect(response: httpx.Response, status: int, label: str) -> dict[str, Any]:
    if response.status_code != status:
        code = "unknown"
        try:
            code = str(response.json().get("code") or code)
        except (ValueError, AttributeError):
            pass
        raise VerificationError(f"{label} failed: HTTP {response.status_code}, code={code}")
    if not response.content:
        return {}
    value = response.json()
    if not isinstance(value, dict):
        raise VerificationError(f"{label} returned a non-object response")
    return value


def _pkce_login(
    client: httpx.Client,
    *,
    issuer: str,
    client_id: str,
    redirect_uri: str,
    username: str,
    password: str,
) -> str:
    verifier = _b64url(secrets.token_bytes(48))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    state = secrets.token_urlsafe(24)
    authorization_url = f"{issuer}/protocol/openid-connect/auth?" + urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid profile",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    page = client.get(authorization_url)
    if page.status_code != 200:
        raise VerificationError(f"{username} authorization page failed: HTTP {page.status_code}")
    parser = _LoginFormParser()
    parser.feed(page.text)
    if not parser.action:
        raise VerificationError(f"{username} login form was not found")
    # Keycloak intentionally marks its reference-realm cookies Secure even on
    # localhost. Browsers treat localhost as a secure context, while httpx
    # follows the stricter generic HTTP cookie rule, so forward only the
    # cookies just issued by this isolated local login transaction.
    login_cookie = "; ".join(f"{cookie.name}={cookie.value}" for cookie in client.cookies.jar)
    login = client.post(
        parser.action,
        data={"username": username, "password": password, "credentialId": ""},
        headers={"Cookie": login_cookie},
        follow_redirects=False,
    )
    if login.status_code not in {302, 303}:
        raise VerificationError(f"{username} login was rejected: HTTP {login.status_code}")
    location = login.headers.get("location", "")
    query = parse_qs(urlparse(location).query)
    if query.get("state", [""])[0] != state or not query.get("code"):
        raise VerificationError(f"{username} authorization redirect was invalid")
    token = client.post(
        f"{issuer}/protocol/openid-connect/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code": query["code"][0],
            "code_verifier": verifier,
        },
    )
    value = _expect(token, 200, f"{username} PKCE token exchange")
    access_token = value.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise VerificationError(f"{username} token response was incomplete")
    return access_token


def _control_headers(token: str, *, idempotency_key: str = "") -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Agent-ID": "general-office-agent",
        "X-Correlation-ID": f"reference-e2e-{secrets.token_hex(8)}",
    }
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def verify(credentials_path: Path, base_url: str, issuer: str, timeout: float) -> dict[str, Any]:
    issuer_url = urlparse(issuer)
    if issuer_url.scheme != "http" or issuer_url.hostname not in {"localhost", "127.0.0.1"}:
        raise VerificationError("the automated verifier is restricted to the local HTTP reference issuer")
    credentials = json.loads(credentials_path.read_text(encoding="utf-8"))
    redirect_uri = base_url.rstrip("/") + "/"
    with httpx.Client(timeout=15, follow_redirects=False) as client:
        alice_token = _pkce_login(
            client,
            issuer=issuer,
            client_id="xa-console",
            redirect_uri=redirect_uri,
            **credentials["alice"],
        )
        alice_headers = _control_headers(alice_token)
        me = _expect(client.get(f"{base_url}/control/v1/me", headers=alice_headers), 200, "Alice identity")
        if me.get("subject") != "10000000-0000-0000-0000-000000000001":
            raise VerificationError("Alice immutable subject was not preserved")
        if "general-office-agent" not in me.get("available_agents", []):
            raise VerificationError("Alice assignment was not applied")

        create = _expect(
            client.post(
                f"{base_url}/control/v1/tickets",
                headers=alice_headers,
                json={
                    "title": "Reference PKCE two-person recovery",
                    "description": "Created by Alice and compensated only after Dora approval.",
                    "priority": "high",
                    "data_domain": "engineering_docs",
                },
            ),
            201,
            "ticket creation",
        )
        effect_id = str(create.get("effect_id") or "")
        if not effect_id or create.get("undo_status") != "available":
            raise VerificationError("ticket creation did not produce an available effect")

        undo_url = f"{base_url}/control/v1/effects/{effect_id}/undo-requests"
        undo_headers = _control_headers(alice_token, idempotency_key=f"undo-{effect_id}")
        undo_body = {"reason": "Reference ticket was intentionally created for recovery verification."}
        undo = _expect(
            client.post(undo_url, headers=undo_headers, json=undo_body),
            201,
            "Undo request",
        )
        request_id = str(undo.get("request_id") or "")
        if not request_id:
            raise VerificationError("Undo request returned no request ID")
        undo_replay = _expect(
            client.post(undo_url, headers=undo_headers, json=undo_body),
            200,
            "Undo idempotent replay",
        )
        if undo_replay.get("request_id") != request_id or undo_replay.get("created") is not False:
            raise VerificationError("Undo idempotency did not preserve the original request")

        self_decision = client.post(
            f"{base_url}/control/v1/undo-requests/{request_id}/decision",
            headers=alice_headers,
            json={"decision": "approve", "reason": "Self approval must fail."},
        )
        if self_decision.status_code != 403:
            raise VerificationError(f"Alice self approval was not rejected: HTTP {self_decision.status_code}")

        # A fresh HTTP client gives Dora an independent Keycloak session.
    with httpx.Client(timeout=15, follow_redirects=False) as dora_client:
        dora_token = _pkce_login(
            dora_client,
            issuer=issuer,
            client_id="xa-console",
            redirect_uri=redirect_uri,
            **credentials["dora"],
        )
        dora_headers = _control_headers(dora_token)
        pending = _expect(
            dora_client.get(f"{base_url}/control/v1/undo-requests?status=pending", headers=dora_headers),
            200,
            "Dora approval queue",
        )
        if request_id not in {item.get("request_id") for item in pending.get("items", [])}:
            raise VerificationError("Dora could not see the pending request")
        _expect(
            dora_client.post(
                f"{base_url}/control/v1/undo-requests/{request_id}/decision",
                headers=dora_headers,
                json={"decision": "approve", "reason": "Independent security approval for reference recovery."},
            ),
            200,
            "Dora approval",
        )

        deadline = time.monotonic() + timeout
        final: dict[str, Any] = {}
        while time.monotonic() < deadline:
            final = _expect(
                dora_client.get(f"{base_url}/control/v1/effects/{effect_id}", headers=dora_headers),
                200,
                "effect polling",
            )
            if final.get("status") == "compensated":
                break
            time.sleep(0.5)
        if final.get("status") != "compensated":
            raise VerificationError(f"effect did not compensate before timeout; status={final.get('status')}")
        if final.get("trace_id") == final.get("compensation_trace_id"):
            raise VerificationError("original and compensation traces were not separated")

    return {
        "status": "passed",
        "flow": "authorization_code_pkce -> token_exchange -> effect -> independent_approval -> worker_compensation",
        "alice_subject_verified": True,
        "alice_self_approval_rejected": True,
        "undo_idempotency_verified": True,
        "dora_independent_approval": True,
        "effect_status": "compensated",
        "separate_traces": True,
        "tokens_persisted_or_printed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--credentials", type=Path, default=DEFAULT_CREDENTIALS)
    parser.add_argument("--base-url", default="http://localhost:13080")
    parser.add_argument("--issuer", default="http://localhost:13081/realms/xa-guard")
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    try:
        result = verify(args.credentials, args.base_url.rstrip("/"), args.issuer.rstrip("/"), args.timeout)
    except (OSError, KeyError, ValueError, httpx.HTTPError, VerificationError) as exc:
        raise SystemExit(f"REFERENCE E2E FAILED: {exc}") from None
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
