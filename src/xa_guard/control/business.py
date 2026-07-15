"""Async client for the fixed reference business API surface."""

from __future__ import annotations

from typing import Any


class BusinessError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class BusinessClient:
    def __init__(self, base_url: str, api_key: str, client: Any | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.client = client

    async def start(self) -> None:
        if self.client is None:
            import httpx

            self.client = httpx.AsyncClient(timeout=10)

    async def close(self) -> None:
        if self.client is not None:
            await self.client.aclose()

    async def ready(self) -> bool:
        if self.client is None:
            return False
        try:
            response = await self.client.get(self.base_url + "/readyz")
            return response.status_code == 200
        except Exception:
            return False

    async def create_ticket(
        self, *, effect_id: str, trace_id: str, tenant_id: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/tickets",
            headers={"X-XA-Effect-ID": effect_id, "Idempotency-Key": effect_id, "X-Correlation-ID": trace_id},
            json={**arguments, "tenant_id": tenant_id},
        )

    async def get_ticket(self, *, ticket_id: str, tenant_id: str, trace_id: str) -> dict[str, Any]:
        return await self._request(
            "GET", f"/tickets/{ticket_id}", params={"tenant_id": tenant_id}, headers={"X-Correlation-ID": trace_id}
        )

    async def get_by_effect(self, *, effect_id: str, trace_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/tickets/by-effect/{effect_id}", headers={"X-Correlation-ID": trace_id})

    async def cancel_ticket(
        self, *, ticket_id: str, tenant_id: str, reason: str, idempotency_key: str, trace_id: str
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"/tickets/{ticket_id}/cancel",
            headers={"Idempotency-Key": idempotency_key, "X-Correlation-ID": trace_id},
            json={"tenant_id": tenant_id, "reason": reason},
        )

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json", **kwargs.pop("headers", {})}
        try:
            response = await self.client.request(method, self.base_url + path, headers=headers, **kwargs)
        except Exception as exc:
            raise BusinessError("network_error", retryable=True) from exc
        try:
            value = response.json()
        except ValueError as exc:
            raise BusinessError("invalid_downstream_response", retryable=response.status_code >= 500) from exc
        if response.is_success and value.get("ok") is True:
            return value
        if response.status_code == 429:
            raise BusinessError("rate_limited", retryable=True)
        if response.status_code >= 500:
            raise BusinessError("upstream_error", retryable=True)
        raise BusinessError(str(value.get("code") or "downstream_rejected"), retryable=False)
