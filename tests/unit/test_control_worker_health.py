from __future__ import annotations

from types import SimpleNamespace

from starlette.testclient import TestClient

from xa_guard.control.worker import CompensationWorker, create_health_app


class _Store:
    pool = None

    def __init__(self, ready: bool) -> None:
        self.value = ready

    async def ready(self) -> bool:
        return self.value


class _Dependency:
    def __init__(self, ready: bool) -> None:
        self.value = ready

    async def ready(self) -> bool:
        return self.value


def _worker(*, store: bool = True, provider: bool = True, business: bool = True):
    runtime = SimpleNamespace(
        store=_Store(store),
        key_provider=_Dependency(provider),
        business=_Dependency(business),
    )
    return CompensationWorker(runtime, worker_id="worker-test")


def test_worker_livez_only_checks_process() -> None:
    with TestClient(create_health_app(_worker(store=False, provider=False, business=False))) as client:
        response = client.get("/livez")

    assert response.status_code == 200
    assert response.json() == {"status": "live", "worker_id": "worker-test"}


def test_worker_readyz_checks_store_provider_and_business() -> None:
    with TestClient(create_health_app(_worker(provider=False))) as client:
        failed = client.get("/readyz")
    with TestClient(create_health_app(_worker())) as client:
        ready = client.get("/readyz")

    assert failed.status_code == 503
    assert failed.json()["checks"]["key_provider"] is False
    assert ready.status_code == 200
    assert all(ready.json()["checks"].values())
