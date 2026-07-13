"""Business HTTP API MCP adapter.

This target exposes a tiny fixed MCP surface over a real downstream HTTP API:

    python -m demo.targets.business_api_target

Configuration is loaded from process environment first, then from the repository
root `.env` file. Secrets are used only for outbound Authorization headers and
are never returned to the caller.
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TIMEOUT_SECONDS = 10.0
MAX_RESPONSE_BYTES = 64 * 1024
MAX_TEXT_CHARS = 4000

_REQUIRED_KEYS = ("BUSINESS_API_BASE_URL", "BUSINESS_API_KEY")
_TRUE_VALUES = {"1", "true", "yes", "y", "on"}
_SECRET_KEY_MARKERS = (
    "authorization",
    "bearer",
    "cookie",
    "credential",
    "password",
    "private",
    "secret",
    "signature",
    "token",
    "api_key",
)


class BusinessApiConfigError(RuntimeError):
    """Raised when the local business API configuration is unsafe or missing."""


@dataclass(frozen=True)
class BusinessApiSettings:
    base_url: str
    api_key: str
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    allow_insecure_local: bool = False


def _parse_env_line(line: str) -> tuple[str, str] | None:
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        return None
    key, value = line.split("=", 1)
    key = key.strip()
    if not key:
        return None
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return key, value


def read_dotenv(path: str | Path) -> dict[str, str]:
    """Read a small KEY=value .env file without expanding shell syntax."""
    p = Path(path)
    if not p.exists():
        return {}
    values: dict[str, str] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        parsed = _parse_env_line(line)
        if parsed is not None:
            key, value = parsed
            values[key] = value
    return values


def _as_bool(value: str) -> bool:
    return value.strip().lower() in _TRUE_VALUES


def _setting(
    key: str,
    *,
    env: Mapping[str, str],
    dotenv_values: Mapping[str, str],
) -> str:
    raw = env.get(key)
    if raw is not None and str(raw).strip():
        return str(raw).strip()
    return str(dotenv_values.get(key) or "").strip()


def _validate_endpoint(base_url: str, *, allow_insecure_local: bool) -> str:
    parsed = urllib.parse.urlparse(base_url)
    if not parsed.scheme or not parsed.netloc:
        raise BusinessApiConfigError("BUSINESS_API_BASE_URL must be an absolute URL")
    host = parsed.hostname or ""
    if parsed.scheme == "https":
        return base_url.rstrip("/")
    if parsed.scheme == "http" and allow_insecure_local and host in {"127.0.0.1", "localhost", "::1"}:
        return base_url.rstrip("/")
    raise BusinessApiConfigError(
        "BUSINESS_API_BASE_URL must use https, except http://127.0.0.1 when "
        "BUSINESS_API_ALLOW_INSECURE_LOCAL=true"
    )


def load_business_api_settings(
    *,
    repo_root: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    env_file: str | Path | None = None,
) -> BusinessApiSettings:
    """Load settings with environment variables taking precedence over `.env`."""
    env_map = os.environ if env is None else env
    root = Path(repo_root).resolve() if repo_root is not None else REPO_ROOT
    configured_env_file = str(env_map.get("BUSINESS_API_ENV_FILE") or "").strip()
    dotenv_path = Path(env_file) if env_file is not None else Path(configured_env_file or root / ".env")
    dotenv_values = read_dotenv(dotenv_path)

    missing = [
        key
        for key in _REQUIRED_KEYS
        if not _setting(key, env=env_map, dotenv_values=dotenv_values)
    ]
    if missing:
        raise BusinessApiConfigError(
            "business API configuration missing required keys: " + ", ".join(missing)
        )

    timeout_raw = _setting(
        "BUSINESS_API_TIMEOUT_SECONDS",
        env=env_map,
        dotenv_values=dotenv_values,
    ) or str(DEFAULT_TIMEOUT_SECONDS)
    try:
        timeout = float(timeout_raw)
    except ValueError as exc:
        raise BusinessApiConfigError("BUSINESS_API_TIMEOUT_SECONDS must be a number") from exc
    if timeout <= 0:
        raise BusinessApiConfigError("BUSINESS_API_TIMEOUT_SECONDS must be positive")

    allow_insecure_local = _as_bool(
        _setting("BUSINESS_API_ALLOW_INSECURE_LOCAL", env=env_map, dotenv_values=dotenv_values)
    )
    base_url = _validate_endpoint(
        _setting("BUSINESS_API_BASE_URL", env=env_map, dotenv_values=dotenv_values),
        allow_insecure_local=allow_insecure_local,
    )
    return BusinessApiSettings(
        base_url=base_url,
        api_key=_setting("BUSINESS_API_KEY", env=env_map, dotenv_values=dotenv_values),
        timeout_seconds=timeout,
        allow_insecure_local=allow_insecure_local,
    )


def _is_secret_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(marker in normalized for marker in _SECRET_KEY_MARKERS)


def redact_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            redacted[key_text] = "[REDACTED]" if _is_secret_key(key_text) else redact_secrets(item)
        return redacted
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, tuple):
        return [redact_secrets(item) for item in value]
    return value


def _request_id(headers: Any) -> str:
    for key in ("x-request-id", "x-correlation-id", "request-id", "correlation-id"):
        value = headers.get(key)
        if value:
            return str(value)
    return ""


def _http_error_type(status: int) -> str:
    if status in {401, 403}:
        return "auth_error"
    if status == 429:
        return "rate_limited"
    if 500 <= status <= 599:
        return "upstream_error"
    return "http_error"


def _decode_body(payload: bytes, content_type: str) -> Any:
    text = payload.decode("utf-8", errors="replace")
    if "json" in content_type.lower():
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    return {"text": text[:MAX_TEXT_CHARS], "content_type": content_type}


class BusinessApiClient:
    def __init__(self, settings: BusinessApiSettings) -> None:
        self.settings = settings

    def get_status(self, *, include_details: bool = False) -> dict[str, Any]:
        return self._request(
            "GET",
            "/status",
            query={"include_details": "true"} if include_details else None,
        )

    def query_record(
        self,
        *,
        record_id: str,
        tenant_id: str = "",
        include_history: bool = False,
    ) -> dict[str, Any]:
        query: dict[str, str] = {}
        if tenant_id:
            query["tenant_id"] = tenant_id
        if include_history:
            query["include_history"] = "true"
        return self._request(
            "GET",
            f"/records/{urllib.parse.quote(record_id, safe='')}",
            query=query or None,
        )

    def submit_ticket(
        self,
        *,
        title: str,
        description: str,
        priority: str = "normal",
        record_id: str = "",
    ) -> dict[str, Any]:
        body = {
            "title": title,
            "description": description,
            "priority": priority,
        }
        if record_id:
            body["record_id"] = record_id
        return self._request("POST", "/tickets", body=body)

    def cancel_ticket(self, *, ticket_id: str, reason: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/tickets/{urllib.parse.quote(ticket_id, safe='')}/cancel",
            body={"reason": reason},
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        query: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        url = self.settings.base_url + path
        if query:
            url += "?" + urllib.parse.urlencode(query)

        payload = None
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.settings.api_key}",
            "User-Agent": "xa-guard-business-api-adapter/0.1",
        }
        if body is not None:
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(url, data=payload, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.settings.timeout_seconds) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                truncated = len(raw) > MAX_RESPONSE_BYTES
                raw = raw[:MAX_RESPONSE_BYTES]
                body_value = _decode_body(raw, response.headers.get("content-type", ""))
                return {
                    "ok": True,
                    "status": int(getattr(response, "status", 200)),
                    "request_id": _request_id(response.headers),
                    "body": redact_secrets(body_value),
                    "truncated": truncated,
                }
        except urllib.error.HTTPError as exc:
            return {
                "ok": False,
                "status": int(exc.code),
                "error_type": _http_error_type(int(exc.code)),
                "request_id": _request_id(exc.headers),
                "message": f"business API returned HTTP {int(exc.code)}",
            }
        except (TimeoutError, socket.timeout):
            return {
                "ok": False,
                "status": 0,
                "error_type": "timeout",
                "request_id": "",
                "message": "business API request timed out",
            }
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", "")
            if isinstance(reason, (TimeoutError, socket.timeout)) or "timed out" in str(reason).lower():
                error_type = "timeout"
                message = "business API request timed out"
            else:
                error_type = "network_error"
                message = "business API network error"
            return {
                "ok": False,
                "status": 0,
                "error_type": error_type,
                "request_id": "",
                "message": message,
            }


app = Server("business-api-target", version="0.1.0")

_GOVERNANCE_ENVELOPE_SCHEMA = {
    "type": "object",
    "description": "XA-Guard governance envelope consumed by the upstream guard.",
    "additionalProperties": True,
}


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="business_get_status",
            description="Fetch sanitized health/status information from the configured business API.",
            inputSchema={
                "type": "object",
                "properties": {
                    "include_details": {"type": "boolean"},
                    "_xa_guard": _GOVERNANCE_ENVELOPE_SCHEMA,
                },
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="business_query_record",
            description="Query one business record by ID through the configured business API.",
            inputSchema={
                "type": "object",
                "properties": {
                    "record_id": {"type": "string"},
                    "tenant_id": {"type": "string"},
                    "include_history": {"type": "boolean"},
                    "_xa_guard": _GOVERNANCE_ENVELOPE_SCHEMA,
                },
                "required": ["record_id"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="business_submit_ticket",
            description="Submit a business support ticket through the configured business API.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "priority": {"type": "string", "enum": ["low", "normal", "high", "urgent"]},
                    "record_id": {"type": "string"},
                    "_xa_guard": _GOVERNANCE_ENVELOPE_SCHEMA,
                },
                "required": ["title", "description"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="business_cancel_ticket",
            description="Compensate a prior ticket submission using its recovery ticket ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticket_id": {"type": "string"},
                    "reason": {"type": "string"},
                    "_xa_guard": _GOVERNANCE_ENVELOPE_SCHEMA,
                },
                "required": ["ticket_id", "reason"],
                "additionalProperties": False,
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    result = _dispatch(name, arguments or {})
    return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, sort_keys=True))]


def _dispatch(name: str, args: dict[str, Any]) -> dict[str, Any]:
    try:
        settings = load_business_api_settings()
    except BusinessApiConfigError as exc:
        return {
            "ok": False,
            "status": 0,
            "error_type": "configuration_error",
            "message": str(exc),
        }

    client = BusinessApiClient(settings)
    try:
        match name:
            case "business_get_status":
                return client.get_status(include_details=bool(args.get("include_details")))
            case "business_query_record":
                record_id = str(args.get("record_id") or "").strip()
                if not record_id:
                    return {
                        "ok": False,
                        "status": 0,
                        "error_type": "validation_error",
                        "message": "record_id is required",
                    }
                return client.query_record(
                    record_id=record_id,
                    tenant_id=str(args.get("tenant_id") or ""),
                    include_history=bool(args.get("include_history")),
                )
            case "business_submit_ticket":
                title = str(args.get("title") or "").strip()
                description = str(args.get("description") or "").strip()
                if not title or not description:
                    return {
                        "ok": False,
                        "status": 0,
                        "error_type": "validation_error",
                        "message": "title and description are required",
                    }
                return client.submit_ticket(
                    title=title,
                    description=description,
                    priority=str(args.get("priority") or "normal"),
                    record_id=str(args.get("record_id") or ""),
                )
            case "business_cancel_ticket":
                ticket_id = str(args.get("ticket_id") or "").strip()
                reason = str(args.get("reason") or "").strip()
                if not ticket_id or not reason:
                    return {
                        "ok": False,
                        "status": 0,
                        "error_type": "validation_error",
                        "message": "ticket_id and reason are required",
                    }
                return client.cancel_ticket(ticket_id=ticket_id, reason=reason)
            case _:
                return {
                    "ok": False,
                    "status": 0,
                    "error_type": "unknown_tool",
                    "message": f"unknown tool: {name}",
                }
    except Exception as exc:
        return {
            "ok": False,
            "status": 0,
            "error_type": "adapter_error",
            "message": f"business API adapter failed: {type(exc).__name__}",
        }


async def _main() -> None:
    async with stdio_server() as (r, w):
        await app.run(r, w, app.create_initialization_options())


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
