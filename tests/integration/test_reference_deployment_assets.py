from __future__ import annotations

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_reference_compose_has_pinned_local_only_identity_effect_stack() -> None:
    value = yaml.safe_load((ROOT / "docker-compose.reference.yml").read_text(encoding="utf-8"))
    services = value["services"]
    assert {"postgres", "keycloak", "xa-guard", "worker", "business-api", "console"}.issubset(services)
    assert "@sha256:" in services["postgres"]["image"]
    assert "@sha256:" in services["keycloak"]["image"]
    assert services["xa-guard"]["ports"] == ["127.0.0.1:13000:8080"]
    assert services["keycloak"]["ports"] == ["127.0.0.1:13081:8080"]
    assert services["console"]["ports"] == ["127.0.0.1:13080:8080"]


def test_reference_realm_has_pkce_stable_exchange_and_no_default_passwords() -> None:
    text = (ROOT / "deploy/reference/keycloak/realm.template.json").read_text(encoding="utf-8")
    realm = json.loads(text)
    clients = {item["clientId"]: item for item in realm["clients"]}
    assert clients["xa-console"]["attributes"]["pkce.code.challenge.method"] == "S256"
    assert clients["general-office-agent"]["attributes"]["standard.token.exchange.enabled"] == "true"
    assert "may_act" not in text
    assert "password" not in {credential["value"] for user in realm["users"] for credential in user["credentials"]}

