"""PostgreSQL-backed ticket API with effect and compensation idempotency."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

log = logging.getLogger("xa_guard.reference.ticket_api")


def _fingerprint(value: dict[str, Any]) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _safe_ticket(row: Any) -> dict[str, Any]:
    return {
        "ticket_id": row["ticket_id"],
        "tenant_id": row["tenant_id"],
        "title": row["title"],
        "description": row["description"],
        "priority": row["priority"],
        "state": row["state"],
        "effect_id": row["create_effect_id"],
        "correlation_id": row["correlation_id"],
        "created_at": row["created_at"].isoformat(),
        "cancelled_at": row["cancelled_at"].isoformat() if row["cancelled_at"] else None,
    }


def _response(payload: dict[str, Any], request: Request, status: int = 200) -> JSONResponse:
    correlation = request.headers.get("x-correlation-id") or str(uuid.uuid4())
    return JSONResponse(payload, status_code=status, headers={"X-Correlation-ID": correlation})


async def _authenticate(request: Request) -> JSONResponse | None:
    header = request.headers.get("authorization", "")
    expected = "Bearer " + request.app.state.api_key
    if not hmac.compare_digest(header, expected):
        return _response({"ok": False, "code": "unauthorized", "message": "valid service credential required"}, request, 401)
    return None


async def livez(request: Request) -> JSONResponse:
    return _response({"status": "live"}, request)


async def readyz(request: Request) -> JSONResponse:
    try:
        ok = await request.app.state.pool.fetchval("SELECT to_regclass('xa_reference_tickets') IS NOT NULL")
    except Exception:
        ok = False
    return _response({"status": "ready" if ok else "not_ready"}, request, 200 if ok else 503)


async def create_ticket(request: Request) -> JSONResponse:
    denied = await _authenticate(request)
    if denied:
        return denied
    effect_id = request.headers.get("x-xa-effect-id") or request.headers.get("idempotency-key") or ""
    if not effect_id:
        return _response({"ok": False, "code": "effect_id_required", "message": "X-XA-Effect-ID is required"}, request, 400)
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return _response({"ok": False, "code": "invalid_json", "message": "JSON body required"}, request, 400)
    required = {key: str(body.get(key) or "").strip() for key in ("tenant_id", "title", "description")}
    if not all(required.values()):
        return _response({"ok": False, "code": "invalid_ticket", "message": "tenant_id, title and description are required"}, request, 422)
    value = {**required, "priority": str(body.get("priority") or "normal")}
    fingerprint = _fingerprint(value)
    correlation = request.headers.get("x-correlation-id") or str(uuid.uuid4())
    pool = request.app.state.pool
    async with pool.acquire() as conn, conn.transaction():
        ticket_id = f"TKT-{uuid.uuid4().hex[:12].upper()}"
        row = await conn.fetchrow(
            """
            INSERT INTO xa_reference_tickets(ticket_id,tenant_id,title,description,priority,state,
              create_effect_id,create_fingerprint,correlation_id)
            VALUES($1,$2,$3,$4,$5,'open',$6,$7,$8)
            ON CONFLICT (create_effect_id) DO NOTHING RETURNING *
            """,
            ticket_id,
            value["tenant_id"],
            value["title"],
            value["description"],
            value["priority"],
            effect_id,
            fingerprint,
            correlation,
        )
        if row is None:
            existing = await conn.fetchrow(
                "SELECT * FROM xa_reference_tickets WHERE create_effect_id=$1", effect_id
            )
            if existing["create_fingerprint"] != fingerprint:
                return _response({"ok": False, "code": "idempotency_conflict", "message": "effect_id was used with different ticket parameters"}, request, 409)
            return _response({"ok": True, "body": _safe_ticket(existing), "idempotent_replay": True}, request)
    log.info("ticket_created ticket_id=%s effect_id=%s correlation_id=%s", ticket_id, effect_id, correlation)
    return _response({"ok": True, "body": _safe_ticket(row), "idempotent_replay": False}, request, 201)


async def get_ticket(request: Request) -> JSONResponse:
    denied = await _authenticate(request)
    if denied:
        return denied
    tenant_id = request.query_params.get("tenant_id", "")
    row = await request.app.state.pool.fetchrow(
        "SELECT * FROM xa_reference_tickets WHERE ticket_id=$1 AND tenant_id=$2",
        request.path_params["ticket_id"],
        tenant_id,
    )
    if row is None:
        return _response({"ok": False, "code": "not_found", "message": "ticket not found"}, request, 404)
    return _response({"ok": True, "body": _safe_ticket(row)}, request)


async def get_by_effect(request: Request) -> JSONResponse:
    denied = await _authenticate(request)
    if denied:
        return denied
    row = await request.app.state.pool.fetchrow(
        "SELECT * FROM xa_reference_tickets WHERE create_effect_id=$1", request.path_params["effect_id"]
    )
    if row is None:
        return _response({"ok": False, "code": "not_found", "message": "ticket not found"}, request, 404)
    return _response({"ok": True, "body": _safe_ticket(row)}, request)


async def cancel_ticket(request: Request) -> JSONResponse:
    denied = await _authenticate(request)
    if denied:
        return denied
    idem = request.headers.get("idempotency-key", "")
    if not idem:
        return _response({"ok": False, "code": "idempotency_key_required", "message": "Idempotency-Key is required"}, request, 400)
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return _response({"ok": False, "code": "invalid_json", "message": "JSON body required"}, request, 400)
    tenant_id = str(body.get("tenant_id") or "")
    if not tenant_id or not str(body.get("reason") or "").strip():
        return _response({"ok": False, "code": "invalid_cancel", "message": "tenant_id and reason are required"}, request, 422)
    pool = request.app.state.pool
    cancel_fingerprint = _fingerprint(
        {"tenant_id": tenant_id, "reason": str(body["reason"]).strip(), "idempotency_key": idem}
    )
    async with pool.acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            "SELECT * FROM xa_reference_tickets WHERE ticket_id=$1 AND tenant_id=$2 FOR UPDATE",
            request.path_params["ticket_id"],
            tenant_id,
        )
        if row is None:
            return _response({"ok": False, "code": "not_found", "message": "ticket not found"}, request, 404)
        if row["state"] == "cancelled":
            if hmac.compare_digest(str(row["cancel_fingerprint"] or ""), cancel_fingerprint):
                return _response({"ok": True, "body": _safe_ticket(row), "idempotent_replay": True}, request)
            return _response({"ok": False, "code": "compensation_conflict", "message": "ticket was cancelled by a different idempotency context"}, request, 409)
        row = await conn.fetchrow(
            "UPDATE xa_reference_tickets SET state='cancelled',cancel_idempotency_key=$1,cancel_fingerprint=$2,cancelled_at=now() "
            "WHERE ticket_id=$3 RETURNING *",
            idem,
            cancel_fingerprint,
            row["ticket_id"],
        )
    log.info("ticket_cancelled ticket_id=%s correlation_id=%s", row["ticket_id"], request.headers.get("x-correlation-id", ""))
    return _response({"ok": True, "body": _safe_ticket(row), "idempotent_replay": False}, request)


def create_app() -> Starlette:
    @asynccontextmanager
    async def lifespan(app: Starlette):
        import asyncpg

        dsn_path = os.getenv("XA_GUARD_DATABASE_URL_FILE", "")
        dsn = open(dsn_path, encoding="utf-8").read().strip() if dsn_path else os.environ["XA_GUARD_DATABASE_URL"]
        key_path = os.getenv("REFERENCE_BUSINESS_API_KEY_FILE", "")
        app.state.api_key = open(key_path, encoding="utf-8").read().strip() if key_path else os.environ["REFERENCE_BUSINESS_API_KEY"]
        app.state.pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
        try:
            yield
        finally:
            await app.state.pool.close()

    return Starlette(
        routes=[
            Route("/livez", livez),
            Route("/readyz", readyz),
            Route("/tickets", create_ticket, methods=["POST"]),
            Route("/tickets/by-effect/{effect_id}", get_by_effect, methods=["GET"]),
            Route("/tickets/{ticket_id}", get_ticket, methods=["GET"]),
            Route("/tickets/{ticket_id}/cancel", cancel_ticket, methods=["POST"]),
        ],
        lifespan=lifespan,
    )


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run("xa_guard.reference.ticket_api:app", host="0.0.0.0", port=int(os.getenv("PORT", "8081")))


if __name__ == "__main__":
    main()
