from __future__ import annotations

from xa_guard.control.oidc import OIDCSettings, OIDCVerifier


def _verifier() -> OIDCVerifier:
    return OIDCVerifier(
        OIDCSettings(
            issuer="https://id.example/realms/acme",
            audience="xa-guard-api",
            client_id="xa-guard-api",
            client_secret="secret",
        )
    )


def test_keycloak_profile_maps_immutable_sub_username_azp_groups_and_roles() -> None:
    principal = _verifier()._principal(
        {
            "sub": "immutable-user-id",
            "preferred_username": "alice",
            "azp": "general-office-agent",
            "tenant_id": "acme-corp",
            "groups": ["engineering-team"],
            "scope": "openid profile",
            "realm_access": {"roles": ["undo.request"]},
            "resource_access": {"xa-guard-api": {"roles": ["ticket.create"]}},
        },
        "raw-token",
    )
    assert principal.subject == "immutable-user-id"
    assert principal.username == "alice"
    assert principal.agent_id == "general-office-agent"
    assert principal.groups == ("engineering-team",)
    assert set(principal.roles) == {"undo.request", "ticket.create"}


def test_external_sts_actor_claim_takes_precedence_over_azp() -> None:
    principal = _verifier()._principal(
        {
            "sub": "human-id",
            "azp": "keycloak-client",
            "act": {"sub": "external-agent"},
            "tenant_id": "acme-corp",
        },
        "raw-token",
    )
    assert principal.agent_id == "external-agent"

