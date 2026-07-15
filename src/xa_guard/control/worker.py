"""Lease-based, multi-replica compensation worker and prepared-effect reconciler."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
import os
import socket
import uuid
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route

from xa_guard.control.business import BusinessError
from xa_guard.control.contracts import contract_succeeded, resolve_pointer
from xa_guard.control.crypto import CryptoError, sha256_json
from xa_guard.control.models import Principal
from xa_guard.control.runtime import ControlRuntime, build_runtime
from xa_guard.control.store import ConflictError
from xa_guard.types import GateContext

log = logging.getLogger("xa_guard.control.worker")


class WorkerLeaseLost(RuntimeError):
    """The claimed effect is no longer owned by this worker."""


class CompensationWorker:
    def __init__(self, runtime: ControlRuntime, worker_id: str = "") -> None:
        self.runtime = runtime
        self.worker_id = worker_id or f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
        self.lease_seconds = int(os.getenv("XA_GUARD_WORKER_LEASE_SECONDS", "60"))
        self.heartbeat_seconds = int(os.getenv("XA_GUARD_WORKER_HEARTBEAT_SECONDS", "20"))
        self.poll_seconds = float(os.getenv("XA_GUARD_WORKER_POLL_SECONDS", "1"))

    async def run_forever(self) -> None:
        await self.runtime.start(oidc=False)
        try:
            while True:
                worked = await self.run_once()
                await self.runtime.service.reconcile_once()
                if not worked:
                    await asyncio.sleep(self.poll_seconds)
        finally:
            await self.runtime.close()

    async def run_once(self) -> bool:
        row = await self.runtime.store.claim_work(self.worker_id, self.lease_seconds)
        if row is None:
            return False
        heartbeat = asyncio.create_task(self._heartbeat(row["effect_id"]))
        compensation = asyncio.create_task(self._compensate(row))
        try:
            done, _pending = await asyncio.wait(
                {heartbeat, compensation}, return_when=asyncio.FIRST_COMPLETED
            )
            if compensation in done and not compensation.cancelled() and compensation.exception() is None:
                # complete_work is lease-guarded.  A heartbeat can observe the
                # resulting compensated state as "lost" in the same event-loop
                # turn, but the completed transaction remains authoritative.
                await compensation
            elif heartbeat in done:
                compensation.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await compensation
                try:
                    await heartbeat
                except Exception as exc:
                    raise WorkerLeaseLost("worker lease was lost") from exc
                raise WorkerLeaseLost("worker heartbeat stopped unexpectedly")
            else:
                await compensation
        except WorkerLeaseLost:
            # Another worker (or an operator) now owns the state transition.  Do
            # not overwrite it with a failure from the stale lease holder.
            log.warning("compensation abandoned after lease loss effect_id=%s", row["effect_id"])
        except BusinessError as exc:
            await self._fail_if_owned(row, exc.retryable, exc.code)
        except CryptoError:
            await self._fail_if_owned(row, False, "internal_authorization_invalid")
        except ConflictError:
            log.warning("compensation state abandoned after lease conflict effect_id=%s", row["effect_id"])
        except Exception as exc:  # noqa: BLE001 - worker must persist a sanitized terminal/retry state
            log.exception("compensation failed effect_id=%s", row["effect_id"])
            await self._fail_if_owned(row, False, type(exc).__name__.lower())
        finally:
            compensation.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await compensation
            heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await heartbeat
        return True

    async def _fail_if_owned(self, row: dict[str, Any], retryable: bool, error_code: str) -> None:
        try:
            await self.runtime.store.fail_work(row, self.worker_id, retryable, error_code)
        except ConflictError:
            log.warning("failure state not written after lease loss effect_id=%s", row["effect_id"])

    async def _compensate(self, row: dict[str, Any]) -> None:
        token = str(row.get("internal_authorization") or "")
        claims = self.runtime.service.internal_authorization.verify(
            token,
            expected={
                "effect_id": row["effect_id"],
                "request_id": row["request_id"],
                "approver_sub": row["approver_sub"],
                "tenant_id": row["tenant_id"],
                "parameters_sha256": row["compensation_args_sha256"],
            },
        )
        parameters = dict(claims.get("parameters") or {})
        if sha256_json(parameters) != row["compensation_args_sha256"]:
            raise CryptoError("compensation parameter hash mismatch")
        principal = Principal(
            subject=str(claims.get("authorization_sub") or claims["approver_sub"]),
            username=str(claims.get("authorization_username") or claims["approver_username"]),
            tenant_id=str(claims["tenant_id"]),
            agent_id=str(claims["agent_id"]),
            issuer="xa-guard-internal-authorization",
            token_id_hash=sha256_json(token),
            roles=tuple(claims.get("roles") or ()),
            groups=tuple(claims.get("groups") or ()),
        )
        contract = dict(row["contract_snapshot"])
        compensation_tool = str(contract["compensation_tool"])
        await self.runtime.service.authorize(principal, compensation_tool, row["data_domain"])
        recovery = await self.runtime.store.decrypt_recovery(row)
        root = {"recovery": recovery, "request": parameters}
        arguments = {
            key: resolve_pointer(root, expression)
            if isinstance(expression, str) and expression.startswith("$")
            else expression
            for key, expression in dict(contract["compensation_arguments"]).items()
        }
        ctx = self.runtime.service._context(principal, compensation_tool, arguments, row["data_domain"])
        ctx.operation_kind = "compensation"
        ctx.compensates_effect_id = row["effect_id"]

        async def execute(active: GateContext) -> dict[str, Any]:
            return await self.runtime.business.cancel_ticket(
                ticket_id=str(arguments["ticket_id"]),
                tenant_id=row["tenant_id"],
                reason=str(arguments["reason"]),
                idempotency_key=row["request_id"],
                trace_id=active.trace_id,
            )

        result = await self.runtime.service._run_confirmed(
            ctx, execute, principal.username, "signed Undo approval"
        )
        if not result.allowed or not contract_succeeded(
            self.runtime.service.contracts.contracts[compensation_tool], result.tool_result
        ):
            raise BusinessError("compensation_not_successful", retryable=False)
        await self.runtime.store.complete_work(row, self.worker_id, ctx.trace_id)

    async def _heartbeat(self, effect_id: str) -> None:
        while True:
            await asyncio.sleep(self.heartbeat_seconds)
            if not await self.runtime.store.heartbeat(effect_id, self.worker_id, self.lease_seconds):
                raise RuntimeError("worker lease was lost")


async def _provider_ready(runtime: ControlRuntime) -> bool:
    provider = getattr(runtime, "key_provider", None) or getattr(runtime.store, "key_provider", None)
    if provider is None:
        return True
    check = getattr(provider, "ready", None)
    if check is None:
        return True
    value = check()
    return bool(await value) if inspect.isawaitable(value) else bool(value)


def create_health_app(worker: CompensationWorker) -> Starlette:
    async def livez(_request: Request) -> JSONResponse:
        return JSONResponse({"status": "live", "worker_id": worker.worker_id})

    async def readyz(_request: Request) -> JSONResponse:
        database_ready = getattr(worker.runtime.store, "database_ready", worker.runtime.store.ready)
        store_ok = await database_ready()
        provider_ok = await _provider_ready(worker.runtime)
        business_ok = await worker.runtime.business.ready()
        ready = store_ok and provider_ok and business_ok
        return JSONResponse(
            {
                "status": "ready" if ready else "not_ready",
                "checks": {
                    "postgresql": store_ok,
                    "key_provider": provider_ok,
                    "business_api": business_ok,
                },
            },
            status_code=200 if ready else 503,
        )

    async def metrics(_request: Request) -> PlainTextResponse:
        pool = worker.runtime.store.pool
        if pool is None:
            return PlainTextResponse("# worker storage is not connected\n", status_code=503)
        queue = await pool.fetchval(
            "SELECT count(*) FROM xa_effects WHERE status IN ('approved','retry_wait','compensating')"
        )
        retries = await pool.fetchval("SELECT COALESCE(sum(retry_count),0) FROM xa_effects")
        leases = await pool.fetchval(
            "SELECT count(*) FROM xa_effects WHERE status='compensating' AND lease_until>now()"
        )
        lines = [
            "# HELP xa_guard_worker_queue_depth Compensation work awaiting completion.",
            "# TYPE xa_guard_worker_queue_depth gauge",
            f"xa_guard_worker_queue_depth {queue}",
            "# HELP xa_guard_worker_retries_total Persisted compensation retry attempts.",
            "# TYPE xa_guard_worker_retries_total counter",
            f"xa_guard_worker_retries_total {retries}",
            "# HELP xa_guard_worker_active_leases Active compensation leases.",
            "# TYPE xa_guard_worker_active_leases gauge",
            f"xa_guard_worker_active_leases {leases}",
        ]
        return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")

    return Starlette(routes=[Route("/livez", livez), Route("/readyz", readyz), Route("/metrics", metrics)])


async def main_async() -> None:
    import uvicorn

    worker = CompensationWorker(build_runtime())
    server = uvicorn.Server(
        uvicorn.Config(
            create_health_app(worker),
            host="0.0.0.0",
            port=int(os.getenv("PORT", "8082")),
            log_level=os.getenv("LOG_LEVEL", "info").lower(),
        )
    )
    worker_task = asyncio.create_task(worker.run_forever())
    server_task = asyncio.create_task(server.serve())
    try:
        done, _pending = await asyncio.wait({worker_task, server_task}, return_when=asyncio.FIRST_COMPLETED)
        if worker_task in done:
            await worker_task
        else:
            server.should_exit = True
            await server_task
    finally:
        server.should_exit = True
        worker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker_task
        if not server_task.done():
            await server_task


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
