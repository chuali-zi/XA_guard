"""Generate local-only secrets/realm and operate the reproducible reference stack."""

from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import subprocess
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime" / "reference"
SECRET_DIR = RUNTIME / "secrets"
TEMPLATE = ROOT / "deploy" / "reference" / "keycloak" / "realm.template.json"
COMPOSE = ROOT / "docker-compose.reference.yml"


def _token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)


def _write_once(path: Path, value: str) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    path.write_text(value + "\n", encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o600)
    return value


def bootstrap() -> dict[str, str]:
    SECRET_DIR.mkdir(parents=True, exist_ok=True)
    postgres_password = _write_once(SECRET_DIR / "postgres_password", _token())
    keycloak_admin_password = _write_once(SECRET_DIR / "keycloak_admin_password", _token())
    bff_secret = _write_once(SECRET_DIR / "bff_client_secret", _token(48))
    api_secret = _write_once(SECRET_DIR / "api_client_secret", _token(48))
    _write_once(SECRET_DIR / "business_api_key", _token(48))
    _write_once(SECRET_DIR / "internal_auth_key", base64.b64encode(secrets.token_bytes(32)).decode())
    keyring_path = SECRET_DIR / "kek_keyring"
    if not keyring_path.exists():
        _write_once(
            keyring_path,
            json.dumps({"active": "reference-kek-v1", "keys": {"reference-kek-v1": base64.b64encode(secrets.token_bytes(32)).decode()}}),
        )
    database_url = f"postgresql://xaguard:{quote(postgres_password, safe='')}@postgres:5432/xaguard"
    _write_once(SECRET_DIR / "database_url", database_url)
    credentials_path = RUNTIME / "credentials.json"
    if credentials_path.exists():
        credentials = json.loads(credentials_path.read_text(encoding="utf-8"))
    else:
        credentials = {
            "keycloak_admin": {"username": "kc-admin", "password": keycloak_admin_password},
            "alice": {"username": "alice", "password": _token(18)},
            "dora": {"username": "dora", "password": _token(18)},
            "governance_admin": {"username": "admin", "password": _token(18)},
        }
        credentials_path.write_text(json.dumps(credentials, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if os.name != "nt":
            credentials_path.chmod(0o600)
    replacements = {
        "__BFF_CLIENT_SECRET__": bff_secret,
        "__API_CLIENT_SECRET__": api_secret,
        "__ALICE_PASSWORD__": credentials["alice"]["password"],
        "__DORA_PASSWORD__": credentials["dora"]["password"],
        "__GOVERNANCE_ADMIN_PASSWORD__": credentials["governance_admin"]["password"],
    }
    realm = TEMPLATE.read_text(encoding="utf-8")
    for marker, value in replacements.items():
        realm = realm.replace(marker, value)
    json.loads(realm)
    (RUNTIME / "realm.json").write_text(realm + "\n", encoding="utf-8")
    return credentials


def compose(args: list[str]) -> int:
    env = dict(os.environ)
    env["REFERENCE_RUNTIME"] = ".runtime/reference"
    return subprocess.call(["docker", "compose", "-f", str(COMPOSE), *args], cwd=ROOT, env=env)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["bootstrap", "up", "down", "config", "credentials"])
    parser.add_argument("--no-build", action="store_true")
    args = parser.parse_args()
    bootstrap()
    if args.action == "bootstrap":
        print(f"Reference credentials written to {RUNTIME / 'credentials.json'}")
        return
    if args.action == "credentials":
        print((RUNTIME / "credentials.json").read_text(encoding="utf-8"))
        return
    if args.action == "up":
        extra = [] if args.no_build else ["--build"]
        code = compose(["up", "-d", *extra])
        if code == 0:
            print("Console: http://localhost:13080")
            print("Keycloak: http://localhost:13081")
            print(f"Credentials: {RUNTIME / 'credentials.json'}")
    elif args.action == "down":
        code = compose(["down"])
    else:
        code = compose(["config"])
    raise SystemExit(code)


if __name__ == "__main__":
    main()
