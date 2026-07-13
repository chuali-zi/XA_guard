from demo.targets.business_api_target import BusinessApiClient, BusinessApiSettings


def test_cancel_ticket_uses_fixed_compensation_endpoint_and_reason(monkeypatch):
    client = BusinessApiClient(BusinessApiSettings("https://business.test", "secret", 2.0))
    captured = {}
    def fake_request(method, path, *, body=None, query=None):
        captured.update(method=method, path=path, body=body, query=query)
        return {"ok": True}
    monkeypatch.setattr(client, "_request", fake_request)
    assert client.cancel_ticket(ticket_id="T/42", reason="operator approved") == {"ok": True}
    assert captured == {"method": "POST", "path": "/tickets/T%2F42/cancel", "body": {"reason": "operator approved"}, "query": None}
