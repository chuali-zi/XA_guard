"""Reference HTTP key provider; KEKs remain outside XA-Guard application pods."""

from __future__ import annotations

import base64
import binascii
import hmac
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from xa_guard.control.crypto import CryptoError, Keyring


class KMSRequestError(RuntimeError):
    pass


class KMSAuthenticationError(RuntimeError):
    pass


def _secret(name: str) -> str:
    path = os.getenv(name + "_FILE", "")
    if path:
        return Path(path).read_text(encoding="utf-8").strip()
    value = os.getenv(name, "")
    if not value:
        raise RuntimeError(f"required KMS secret is absent: {name} or {name}_FILE")
    return value


def _authorize(request: Request) -> None:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    expected = request.app.state.auth_token
    if scheme.lower() != "bearer" or not token or not hmac.compare_digest(token, expected):
        raise KMSAuthenticationError("authentication failed")


async def _body(request: Request) -> dict[str, Any]:
    raw = await request.body()
    if not raw or len(raw) > 64 * 1024:
        raise KMSRequestError("invalid request")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KMSRequestError("invalid request") from exc
    if not isinstance(value, dict):
        raise KMSRequestError("invalid request")
    return value


def _decode(value: Any, *, max_bytes: int) -> bytes:
    if not isinstance(value, str) or len(value) > max_bytes * 2:
        raise KMSRequestError("invalid key material")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise KMSRequestError("invalid key material") from exc
    if not decoded or len(decoded) > max_bytes:
        raise KMSRequestError("invalid key material")
    return decoded


def _key_id(value: Any) -> str:
    key_id = str(value or "")
    if not key_id or len(key_id) > 256 or any(ord(char) < 33 for char in key_id):
        raise KMSRequestError("invalid key identifier")
    return key_id


def _response(value: dict[str, Any], status: int = 200) -> JSONResponse:
    return JSONResponse(
        value,
        status_code=status,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


async def error_handler(_request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, KMSAuthenticationError):
        return _response({"code": "unauthorized", "message": "authentication failed"}, 401)
    if isinstance(exc, KMSRequestError):
        return _response({"code": "invalid_request", "message": "request is invalid"}, 400)
    if isinstance(exc, CryptoError):
        return _response({"code": "key_operation_failed", "message": "key operation failed"}, 409)
    return _response({"code": "internal_error", "message": "key service operation failed"}, 500)


async def ready(request: Request) -> JSONResponse:
    _authorize(request)
    return _response(
        {"status": "ready", "active_key_id": request.app.state.keyring.active_key_id}
    )


async def wrap(request: Request) -> JSONResponse:
    _authorize(request)
    value = await _body(request)
    plaintext_key = _decode(value.get("plaintext_key"), max_bytes=32)
    if len(plaintext_key) != 32:
        raise KMSRequestError("invalid key material")
    key_id, wrapped_key = request.app.state.keyring.wrap_key(plaintext_key)
    return _response(
        {
            "key_id": key_id,
            "wrapped_key": base64.b64encode(wrapped_key).decode("ascii"),
        }
    )


async def unwrap(request: Request) -> JSONResponse:
    _authorize(request)
    value = await _body(request)
    plaintext_key = request.app.state.keyring.unwrap_key(
        _key_id(value.get("key_id")),
        _decode(value.get("wrapped_key"), max_bytes=16_384),
    )
    return _response(
        {"plaintext_key": base64.b64encode(plaintext_key).decode("ascii")}
    )


async def rewrap(request: Request) -> JSONResponse:
    _authorize(request)
    value = await _body(request)
    key_id, wrapped_key = request.app.state.keyring.rewrap_key(
        _key_id(value.get("key_id")),
        _decode(value.get("wrapped_key"), max_bytes=16_384),
    )
    return _response(
        {
            "key_id": key_id,
            "wrapped_key": base64.b64encode(wrapped_key).decode("ascii"),
        }
    )


def create_app(
    *, keyring: Keyring | None = None, auth_token: str = ""
) -> Starlette:
    @asynccontextmanager
    async def lifespan(app: Starlette):
        app.state.keyring = keyring or Keyring.from_json(
            _secret("REFERENCE_KMS_KEK_KEYRING")
        )
        app.state.auth_token = auth_token or _secret("REFERENCE_KMS_AUTH_TOKEN")
        if not app.state.auth_token:
            raise RuntimeError("reference KMS authentication token is absent")
        yield

    return Starlette(
        routes=[
            Route("/readyz", ready),
            Route("/v1/wrap", wrap, methods=["POST"]),
            Route("/v1/unwrap", unwrap, methods=["POST"]),
            Route("/v1/rewrap", rewrap, methods=["POST"]),
        ],
        lifespan=lifespan,
        exception_handlers={Exception: error_handler},
    )


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run(
        "xa_guard.reference.kms_api:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8083")),
    )


if __name__ == "__main__":
    main()
