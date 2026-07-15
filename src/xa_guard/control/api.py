"""Bearer-protected REST control plane with tenant isolation and safe errors."""

from __future__ import annotations

import json
import os
import re
import uuid
from contextlib import asynccontextmanager
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.routing import Route

from xa_guard.control.ceiling import CeilingError
from xa_guard.control.contracts import ContractError
from xa_guard.control.oidc import OIDCError, bearer_principal
from xa_guard.control.runtime import build_runtime
from xa_guard.control.service import ServiceError
from xa_guard.control.store import AuthorizationError, ConflictError, NotFoundError, StoreError


def _trace(request: Request) -> str:
    value = getattr(request.state, "trace_id", "")
    if not value:
        value = (
            request.headers.get("x-request-id")
            or request.headers.get("x-correlation-id")
            or str(uuid.uuid4())
        )
        request.state.trace_id = value
    return value


def _json(request: Request, value: Any, status: int = 200) -> JSONResponse:
    return JSONResponse(value, status_code=status, headers={"X-Trace-ID": _trace(request)})


async def _body(request: Request) -> dict[str, Any]:
    try:
        value = await request.json()
    except json.JSONDecodeError as exc:
        raise ConflictError("valid JSON body is required") from exc
    if not isinstance(value, dict):
        raise ConflictError("JSON object body is required")
    return value


async def error_handler(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, OIDCError):
        code, status = exc.code, 401
    elif isinstance(exc, (AuthorizationError, CeilingError)):
        code, status = "forbidden", 403
    elif isinstance(exc, NotFoundError):
        code, status = exc.code, 404
    elif isinstance(exc, (ConflictError, ContractError)):
        code, status = "conflict", 409
    elif isinstance(exc, (StoreError, ServiceError)):
        code, status = getattr(exc, "code", "operation_failed"), 503
    else:
        code, status = "internal_error", 500
    if isinstance(exc, (OIDCError, AuthorizationError, CeilingError)):
        counters = request.app.state.identity_rejections
        counters[code] = int(counters.get(code, 0)) + 1
    # No database, token, recovery, or downstream exception text is returned.
    messages = {
        "invalid_token": "authentication failed",
        "forbidden": "operation is not authorized",
        "not_found": "resource was not found",
        "conflict": "operation conflicts with current resource state",
        "internal_error": "internal operation failed",
        "store_error": "control plane storage is unavailable",
        "service_error": "operation could not be completed",
    }
    return _json(
        request,
        {"code": code, "message": messages.get(code, "operation failed"), "trace_id": _trace(request)},
        status,
    )


async def livez(request: Request) -> JSONResponse:
    return _json(request, {"status": "live"})


async def readyz(request: Request) -> JSONResponse:
    runtime = request.app.state.runtime
    store_ok = await runtime.store.database_ready()
    provider_ok = runtime.key_provider is not None and await runtime.key_provider.ready()
    oidc_ok = bool(runtime.verifier.discovery and runtime.verifier.jwks and runtime.verifier.last_refresh_ok)
    ready = store_ok and provider_ok and oidc_ok
    return _json(
        request,
        {
            "status": "ready" if ready else "not_ready",
            "checks": {
                "postgresql": store_ok,
                "key_provider": provider_ok,
                "oidc_jwks": oidc_ok,
            },
        },
        200 if ready else 503,
    )


async def metrics(request: Request) -> PlainTextResponse:
    runtime = request.app.state.runtime
    rows = await runtime.store.pool.fetch("SELECT status,count(*) AS count FROM xa_effects GROUP BY status")
    undo_rows = await runtime.store.pool.fetch(
        "SELECT status,count(*) AS count FROM xa_undo_requests GROUP BY status"
    )
    queue = await runtime.store.pool.fetchval(
        "SELECT count(*) FROM xa_effects WHERE status IN ('approved','retry_wait','compensating')"
    )
    retries = await runtime.store.pool.fetchval("SELECT COALESCE(sum(retry_count),0) FROM xa_effects")
    assignments = await runtime.store.pool.fetchval(
        "SELECT count(*) FROM xa_assignments WHERE deleted_at IS NULL "
        "AND valid_from<=now() AND (valid_until IS NULL OR valid_until>now())"
    )
    lines = [
        "# HELP xa_guard_jwks_refresh_ok Last JWKS refresh status.",
        "# TYPE xa_guard_jwks_refresh_ok gauge",
        f"xa_guard_jwks_refresh_ok {1 if runtime.verifier.last_refresh_ok else 0}",
        "# HELP xa_guard_compensation_queue_depth Compensation work awaiting completion.",
        "# TYPE xa_guard_compensation_queue_depth gauge",
        f"xa_guard_compensation_queue_depth {queue}",
        "# HELP xa_guard_compensation_retries_total Persisted compensation retry attempts.",
        "# TYPE xa_guard_compensation_retries_total counter",
        f"xa_guard_compensation_retries_total {retries}",
        "# HELP xa_guard_active_assignments Current non-expired dynamic assignments.",
        "# TYPE xa_guard_active_assignments gauge",
        f"xa_guard_active_assignments {assignments}",
        "# HELP xa_guard_effects Current effects by state.",
        "# TYPE xa_guard_effects gauge",
    ]
    lines.extend(f'xa_guard_effects{{status="{row["status"]}"}} {row["count"]}' for row in rows)
    lines.extend(
        (
            "# HELP xa_guard_undo_requests Current Undo requests by state.",
            "# TYPE xa_guard_undo_requests gauge",
        )
    )
    lines.extend(f'xa_guard_undo_requests{{status="{row["status"]}"}} {row["count"]}' for row in undo_rows)
    lines.extend(
        (
            "# HELP xa_guard_identity_rejections_total Process-local identity and assignment rejections.",
            "# TYPE xa_guard_identity_rejections_total counter",
        )
    )
    lines.extend(
        f'xa_guard_identity_rejections_total{{reason="{reason}"}} {count}'
        for reason, count in sorted(request.app.state.identity_rejections.items())
    )
    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")


async def me(request: Request) -> JSONResponse:
    principal = await bearer_principal(request)
    return _json(request, await request.app.state.runtime.service.me(principal))


async def agents(request: Request) -> JSONResponse:
    principal = await bearer_principal(request)
    return _json(request, {"items": await request.app.state.runtime.service.agents(principal)})


async def create_ticket(request: Request) -> JSONResponse:
    principal = await bearer_principal(request)
    value = await request.app.state.runtime.service.create_ticket(principal, await _body(request))
    return _json(request, value, 201)


async def effects(request: Request) -> JSONResponse:
    principal = await bearer_principal(request)
    if not await request.app.state.runtime.store.effective_assignments(principal, principal.agent_id):
        raise AuthorizationError("an active agent assignment is required")
    items = await request.app.state.runtime.store.list_effects(principal.tenant_id)
    return _json(request, {"items": items})


async def effect_detail(request: Request) -> JSONResponse:
    principal = await bearer_principal(request)
    if not await request.app.state.runtime.store.effective_assignments(principal, principal.agent_id):
        raise AuthorizationError("an active agent assignment is required")
    value = await request.app.state.runtime.store.get_effect(
        principal.tenant_id, request.path_params["effect_id"]
    )
    return _json(request, value)


async def request_undo(request: Request) -> JSONResponse:
    principal = await bearer_principal(request)
    idem = request.headers.get("idempotency-key", "")
    if not idem:
        raise ConflictError("Idempotency-Key is required")
    body = await _body(request)
    reason = str(body.get("reason") or "").strip()
    if not reason:
        raise ConflictError("reason is required")
    value = await request.app.state.runtime.service.request_undo(
        principal, request.path_params["effect_id"], reason, idem
    )
    return _json(request, value, 201 if value["created"] else 200)


async def undo_requests(request: Request) -> JSONResponse:
    principal = await bearer_principal(request)
    if "undo.approve" not in principal.roles:
        raise AuthorizationError("undo.approve role is required")
    if not await request.app.state.runtime.store.effective_assignments(principal, principal.agent_id):
        raise AuthorizationError("an active agent assignment is required")
    status = request.query_params.get("status", "pending")
    items = await request.app.state.runtime.store.list_undo_requests(principal.tenant_id, status)
    return _json(request, {"items": items})


async def decide(request: Request) -> JSONResponse:
    principal = await bearer_principal(request, sensitive=True)
    body = await _body(request)
    decision = str(body.get("decision") or "")
    reason = str(body.get("reason") or "").strip()
    if not reason:
        raise ConflictError("reason is required")
    value = await request.app.state.runtime.service.decide_undo(
        principal, request.path_params["request_id"], decision, reason
    )
    return _json(request, value)


async def retry(request: Request) -> JSONResponse:
    principal = await bearer_principal(request, sensitive=True)
    await request.app.state.runtime.service.retry_failed(principal, request.path_params["request_id"])
    return _json(request, {"request_id": request.path_params["request_id"], "status": "approved"})


async def assignments(request: Request) -> JSONResponse:
    principal = await bearer_principal(request, sensitive=True)
    if "governance.admin" not in principal.roles:
        raise AuthorizationError("governance.admin role is required")
    if request.method == "GET":
        return _json(
            request, {"items": await request.app.state.runtime.store.list_assignments(principal.tenant_id)}
        )
    if request.headers.get("if-none-match") != "*":
        raise ConflictError("If-None-Match: * is required")
    value = await request.app.state.runtime.service.create_assignment(principal, await _body(request))
    return _json(request, value, 201)


async def delete_assignment(request: Request) -> Response:
    principal = await bearer_principal(request, sensitive=True)
    match = re.fullmatch(r'(?:W/)?"v?(\d+)"', request.headers.get("if-match", ""))
    if match is None:
        raise ConflictError("If-Match version is required")
    await request.app.state.runtime.service.delete_assignment(
        principal, request.path_params["assignment_id"], int(match.group(1))
    )
    return Response(status_code=204, headers={"X-Trace-ID": _trace(request)})


def create_app() -> Starlette:
    @asynccontextmanager
    async def lifespan(app: Starlette):
        runtime = build_runtime()
        await runtime.start(oidc=True, migrate=os.getenv("XA_GUARD_AUTO_MIGRATE", "false").lower() == "true")
        app.state.runtime = runtime
        app.state.verifier = runtime.verifier
        try:
            yield
        finally:
            await runtime.close()

    routes = [
        Route("/livez", livez),
        Route("/readyz", readyz),
        Route("/metrics", metrics),
        Route("/control/v1/me", me),
        Route("/control/v1/agents", agents),
        Route("/control/v1/tickets", create_ticket, methods=["POST"]),
        Route("/control/v1/effects", effects),
        Route("/control/v1/effects/{effect_id}", effect_detail),
        Route("/control/v1/effects/{effect_id}/undo-requests", request_undo, methods=["POST"]),
        Route("/control/v1/undo-requests", undo_requests),
        Route("/control/v1/undo-requests/{request_id}/decision", decide, methods=["POST"]),
        Route("/control/v1/undo-requests/{request_id}/retry", retry, methods=["POST"]),
        Route("/control/v1/assignments", assignments, methods=["GET", "POST"]),
        Route("/control/v1/assignments/{assignment_id}", delete_assignment, methods=["DELETE"]),
    ]
    handled_errors = (
        OIDCError,
        AuthorizationError,
        CeilingError,
        NotFoundError,
        ConflictError,
        ContractError,
        StoreError,
        ServiceError,
    )
    app = Starlette(
        routes=routes,
        lifespan=lifespan,
        # Register expected domain failures explicitly so Starlette does not
        # treat a correctly mapped 4xx/503 as an unhandled server exception.
        # Unexpected exceptions still reach the catch-all and retain a 500
        # traceback in server logs while the client sees only the safe shape.
        exception_handlers={
            **{error_type: error_handler for error_type in handled_errors},
            Exception: error_handler,
        },
    )
    app.state.identity_rejections = {}
    return app


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run("xa_guard.control.api:app", host="0.0.0.0", port=int(os.getenv("PORT", "8080")))


if __name__ == "__main__":
    main()
