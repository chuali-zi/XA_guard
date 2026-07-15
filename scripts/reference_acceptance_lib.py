"""Secret-safe helpers shared by Identity + Undo reference acceptance runners."""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx

from verify_reference_e2e import _pkce_login


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.reference.yml"
RUNTIME = ROOT / ".runtime" / "reference"


class AcceptanceFailure(RuntimeError):
    pass


def read_secret(name: str) -> str:
    value = (RUNTIME / "secrets" / name).read_text(encoding="utf-8").strip()
    if not value:
        raise AcceptanceFailure(f"reference secret {name!r} is empty")
    return value


class ReferenceIdentity:
    """Acquire request-scoped human and exchanged Agent tokens without printing them."""

    def __init__(
        self,
        *,
        issuer: str = "http://localhost:13081/realms/xa-guard",
        control_url: str = "http://localhost:13000",
    ) -> None:
        self.issuer = issuer.rstrip("/")
        self.control_url = control_url.rstrip("/")
        self.credentials = json.loads((RUNTIME / "credentials.json").read_text(encoding="utf-8"))

    def human_token(self, username: str) -> str:
        with httpx.Client(timeout=15, follow_redirects=False) as client:
            return _pkce_login(
                client,
                issuer=self.issuer,
                client_id="xa-console",
                redirect_uri="http://localhost:13080/",
                **self.credentials[username],
            )

    def agent_token(
        self,
        username: str,
        *,
        agent_id: str = "general-office-agent",
        secret_name: str = "bff_client_secret",
    ) -> str:
        human = self.human_token(username)
        with httpx.Client(timeout=15) as client:
            response = client.post(
                self.issuer + "/protocol/openid-connect/token",
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                    "subject_token": human,
                    "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
                    "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
                    "client_id": agent_id,
                    "client_secret": read_secret(secret_name),
                    "audience": "xa-guard-api",
                },
            )
        if response.status_code != 200:
            raise AcceptanceFailure(
                f"{username} Agent token exchange failed with HTTP {response.status_code}"
            )
        token = response.json().get("access_token")
        if not isinstance(token, str) or not token:
            raise AcceptanceFailure(f"{username} Agent token exchange returned no token")
        return token

    @staticmethod
    def headers(
        token: str,
        *,
        idempotency_key: str = "",
        agent_id: str = "general-office-agent",
    ) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Agent-ID": agent_id,
            "X-Correlation-ID": f"acceptance-{secrets.token_hex(8)}",
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers


def compose(*args: str, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["REFERENCE_RUNTIME"] = ".runtime/reference"
    env["XA_GUARD_TEST_FAULTS"] = "true"
    return subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE), *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=capture,
        check=check,
    )


def sql(query: str) -> str:
    result = compose(
        "exec",
        "-T",
        "postgres",
        "psql",
        "-X",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        "xaguard",
        "-d",
        "xaguard",
        "-At",
        "-c",
        query,
    )
    return result.stdout.strip()


def arm(service: str, name: str, payload: str = "armed") -> None:
    if not name.replace("-", "").replace("_", "").isalnum():
        raise AcceptanceFailure("invalid fault name")
    code = (
        "from pathlib import Path; "
        "p=Path('/tmp/xa-guard-faults'); p.mkdir(parents=True,exist_ok=True); "
        f"(p/{name!r}).write_text({payload!r},encoding='utf-8')"
    )
    compose("exec", "-T", service, "python", "-c", code)


def wait_url(url: str, *, timeout: float = 90.0, expected: int = 200) -> None:
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        try:
            response = httpx.get(url, timeout=2)
            last = f"HTTP {response.status_code}"
            if response.status_code == expected:
                return
        except httpx.HTTPError as exc:
            last = type(exc).__name__
        time.sleep(0.5)
    raise AcceptanceFailure(f"{url} did not become ready: {last}")


def business_metric(name: str, labels: str) -> int:
    response = httpx.get("http://localhost:13082/metrics", timeout=5)
    response.raise_for_status()
    prefix = f"{name}{{{labels}}} "
    for line in response.text.splitlines():
        if line.startswith(prefix):
            return int(float(line[len(prefix) :]))
    raise AcceptanceFailure(f"business metric is absent: {name}{{{labels}}}")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
