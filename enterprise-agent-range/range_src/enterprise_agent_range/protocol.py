from __future__ import annotations

import json
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import urlparse

from .models import ToolResult
from .systems import RangeState, ToolContext
from .tools import TOOL_DEFINITIONS, execute_tool


LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def build_protocol_state(
    *,
    manifest_root: Path | None = None,
    run_id: str = "protocol-local",
    sut_id: str = "local-protocol",
    environment_hash: str = "sha256:local-protocol",
) -> RangeState:
    return RangeState(
        run_id=run_id,
        sut_id=sut_id,
        environment_hash=environment_hash,
        manifest_root=(manifest_root or Path.cwd()).resolve(),
    )


def _default_case(request: dict[str, Any]) -> dict[str, Any]:
    case = request.get("case")
    if isinstance(case, dict):
        return case
    return {
        "case_id": str(request.get("case_id", "PROTOCOL-LOCAL")),
        "principal": {"principal_id": str(request.get("principal_id", "protocol.local@range.local"))},
        "agent": {"agent_id": str(request.get("agent_id", "protocol-agent"))},
    }


def _tool_result_json(result: ToolResult) -> dict[str, Any]:
    return {
        "tool_name": result.tool_name,
        "output": result.output,
        "side_effect_refs": result.side_effect_refs,
    }


def list_tools_response() -> dict[str, Any]:
    return {"tools": TOOL_DEFINITIONS}


def call_tool_response(state: RangeState, request: dict[str, Any]) -> dict[str, Any]:
    params = request.get("params") if isinstance(request.get("params"), dict) else request
    name = params.get("name") or params.get("tool") or params.get("tool_name")
    if not isinstance(name, str) or not name:
        raise ValueError("tools/call requires a string tool name")
    arguments = params.get("arguments", params.get("args", {}))
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise ValueError("tools/call arguments must be an object")
    trace_id = str(params.get("trace_id", f"trace-{_default_case(params)['case_id']}-protocol"))
    ctx = ToolContext(state=state, case=_default_case(params), trace_id=trace_id)
    return _tool_result_json(execute_tool(ctx, name, arguments))


def handle_protocol_request(state: RangeState, request: dict[str, Any]) -> dict[str, Any]:
    request_id = request.get("id")
    method = request.get("method") or request.get("type")
    try:
        if method == "tools/list":
            result = list_tools_response()
        elif method == "tools/call":
            result = call_tool_response(state, request)
        else:
            raise ValueError(f"unknown protocol method: {method!r}")
        response: dict[str, Any] = {"ok": True, "result": result}
    except KeyError as exc:
        response = {"ok": False, "error": {"code": "unknown_tool", "message": str(exc)}}
    except ValueError as exc:
        response = {"ok": False, "error": {"code": "bad_request", "message": str(exc)}}
    if request_id is not None:
        response["id"] = request_id
    return response


def serve_stdio(
    state: RangeState,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> int:
    input_stream = stdin or sys.stdin
    output_stream = stdout or sys.stdout
    exit_code = 0
    for line in input_stream:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError("request must be an object")
            response = handle_protocol_request(state, request)
        except (json.JSONDecodeError, ValueError) as exc:
            exit_code = 1
            response = {"ok": False, "error": {"code": "bad_request", "message": str(exc)}}
        output_stream.write(json.dumps(response, ensure_ascii=False, sort_keys=True) + "\n")
        output_stream.flush()
    return exit_code


def _read_replay_payload(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        calls = payload
    elif isinstance(payload, dict) and isinstance(payload.get("calls"), list):
        calls = payload["calls"]
    else:
        raise ValueError("IDE replay file must be a JSON list or an object with a calls list")
    if not all(isinstance(call, dict) for call in calls):
        raise ValueError("IDE replay calls must be JSON objects")
    return calls


def replay_ide_file(state: RangeState, path: Path) -> list[dict[str, Any]]:
    responses: list[dict[str, Any]] = []
    for index, call in enumerate(_read_replay_payload(path), start=1):
        request = dict(call)
        request.setdefault("id", index)
        request.setdefault("method", "tools/call")
        responses.append(handle_protocol_request(state, request))
    return responses


class RangeHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], state: RangeState):
        if server_address[0] not in LOCAL_HOSTS:
            raise ValueError("HTTP protocol server is restricted to localhost addresses")
        self.range_state = state
        super().__init__(server_address, RangeHTTPRequestHandler)


class RangeHTTPRequestHandler(BaseHTTPRequestHandler):
    server: RangeHTTPServer

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/healthz":
            self._write_json(HTTPStatus.OK, {"ok": True, "service": "enterprise-agent-range"})
            return
        if path == "/tools":
            self._write_json(HTTPStatus.OK, list_tools_response())
            return
        self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path != "/call":
            self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            request = json.loads(body or "{}")
            if not isinstance(request, dict):
                raise ValueError("request must be an object")
            response = handle_protocol_request(
                self.server.range_state,
                {"method": "tools/call", "params": request, "id": request.get("id")},
            )
            status = HTTPStatus.OK if response.get("ok") else HTTPStatus.BAD_REQUEST
            self._write_json(status, response)
        except (json.JSONDecodeError, ValueError) as exc:
            self._write_json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": {"code": "bad_request", "message": str(exc)}},
            )

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve_http(state: RangeState, *, host: str = "127.0.0.1", port: int = 8765) -> None:
    server = RangeHTTPServer((host, port), state)
    print(f"serving enterprise-agent-range protocol on http://{host}:{server.server_port}", file=sys.stderr)
    try:
        server.serve_forever()
    finally:
        server.server_close()
