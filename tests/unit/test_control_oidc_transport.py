from xa_guard.control.oidc import OIDCSettings, OIDCVerifier


def _settings(**overrides):
    values = {
        "issuer": "http://host.docker.internal:13081/realms/xa-guard",
        "audience": "xa-guard-api",
        "client_id": "xa-guard-api",
        "client_secret": "secret",
        "reference_http_hosts": ("host.docker.internal",),
    }
    values.update(overrides)
    return OIDCSettings(**values)


def test_reference_http_allowlist_is_explicit() -> None:
    verifier = OIDCVerifier(_settings())

    assert verifier._safe_endpoint("http://host.docker.internal:13081/realms/xa-guard")
    assert not verifier._safe_endpoint("http://attacker.invalid/realms/xa-guard")


def test_production_profile_can_require_https_by_emptying_allowlist() -> None:
    verifier = OIDCVerifier(_settings(reference_http_hosts=()))

    assert not verifier._safe_endpoint("http://host.docker.internal:13081/realms/xa-guard")
    assert verifier._safe_endpoint("https://id.example.gov/realms/xa-guard")
