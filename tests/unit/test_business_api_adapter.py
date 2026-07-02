from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from demo.targets import business_api_target as target


@contextmanager
def _fake_business_api(api_key: str = "unit-secret-key"):
    state: dict[str, Any] = {"calls": []}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *args: object) -> None:
            return

        def _send_json(self, status: int, body: dict[str, Any], request_id: str) -> None:
            payload = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("x-request-id", request_id)
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:
            state["calls"].append(
                {
                    "method": "GET",
                    "path": self.path,
                    "authorization": self.headers.get("authorization", ""),
                }
            )
            if self.headers.get("authorization") != f"Bearer {api_key}":
                self._send_json(401, {"error": "bad auth", "token": "server-secret"}, "req-auth")
                return
            if self.path.startswith("/status"):
                self._send_json(
                    200,
                    {
                        "status": "ok",
                        "api_key": "server-secret",
                        "nested": {"token": "server-secret"},
                    },
                    "req-status",
                )
                return
            if self.path.startswith("/records/not-json"):
                payload = b"plain text body"
                self.send_response(200)
                self.send_header("content-type", "text/plain")
                self.send_header("x-correlation-id", "corr-text")
                self.send_header("content-length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            if self.path.startswith("/records/limited"):
                self._send_json(429, {"error": "slow down", "secret": "server-secret"}, "req-429")
                return
            if self.path.startswith("/records/broken"):
                self._send_json(503, {"error": "unavailable", "secret": "server-secret"}, "req-503")
                return
            self._send_json(200, {"record_id": self.path.rsplit("/", 1)[-1], "value": 42}, "req-record")

        def do_POST(self) -> None:
            length = int(self.headers.get("content-length") or "0")
            body = self.rfile.read(length).decode("utf-8")
            state["calls"].append(
                {
                    "method": "POST",
                    "path": self.path,
                    "authorization": self.headers.get("authorization", ""),
                    "body": body,
                }
            )
            if self.headers.get("authorization") != f"Bearer {api_key}":
                self._send_json(403, {"error": "forbidden", "token": "server-secret"}, "req-403")
                return
            self._send_json(201, {"ticket_id": "T-1", "secret": "server-secret"}, "req-ticket")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", state
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_dotenv_loader_reads_repo_file_and_environment_wins(tmp_path: Path):
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "BUSINESS_API_BASE_URL=https://file.example.test",
                "BUSINESS_API_KEY=file-secret",
                "BUSINESS_API_TIMEOUT_SECONDS=4",
            ]
        ),
        encoding="utf-8",
    )

    from_file = target.load_business_api_settings(repo_root=tmp_path, env={})
    assert from_file.base_url == "https://file.example.test"
    assert from_file.api_key == "file-secret"
    assert from_file.timeout_seconds == 4

    from_env = target.load_business_api_settings(
        repo_root=tmp_path,
        env={
            "BUSINESS_API_BASE_URL": "https://env.example.test",
            "BUSINESS_API_KEY": "env-secret",
            "BUSINESS_API_TIMEOUT_SECONDS": "2",
        },
    )
    assert from_env.base_url == "https://env.example.test"
    assert from_env.api_key == "env-secret"
    assert from_env.timeout_seconds == 2


def test_missing_or_insecure_configuration_fails_closed(tmp_path: Path):
    try:
        target.load_business_api_settings(repo_root=tmp_path, env={})
    except target.BusinessApiConfigError as exc:
        message = str(exc)
    else:  # pragma: no cover
        raise AssertionError("missing configuration must fail closed")

    assert "BUSINESS_API_BASE_URL" in message
    assert "BUSINESS_API_KEY" in message
    assert "secret" not in message.lower()

    insecure_env = {
        "BUSINESS_API_BASE_URL": "http://api.example.test",
        "BUSINESS_API_KEY": "unit-secret",
    }
    try:
        target.load_business_api_settings(repo_root=tmp_path, env=insecure_env)
    except target.BusinessApiConfigError as exc:
        assert "https" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("remote http endpoint must be rejected")

    local_env = {
        "BUSINESS_API_BASE_URL": "http://127.0.0.1:12345",
        "BUSINESS_API_KEY": "unit-secret",
        "BUSINESS_API_ALLOW_INSECURE_LOCAL": "true",
    }
    assert target.load_business_api_settings(repo_root=tmp_path, env=local_env).allow_insecure_local is True


def test_client_success_redacts_response_secrets_and_keeps_key_out_of_result():
    with _fake_business_api() as (base_url, state):
        settings = target.BusinessApiSettings(
            base_url=base_url,
            api_key="unit-secret-key",
            timeout_seconds=2,
            allow_insecure_local=True,
        )
        result = target.BusinessApiClient(settings).get_status(include_details=True)

    assert result["ok"] is True
    assert result["request_id"] == "req-status"
    assert result["body"]["status"] == "ok"
    assert result["body"]["api_key"] == "[REDACTED]"
    assert result["body"]["nested"]["token"] == "[REDACTED]"
    assert state["calls"][0]["authorization"] == "Bearer unit-secret-key"
    result_text = json.dumps(result, ensure_ascii=False)
    assert "unit-secret-key" not in result_text
    assert "server-secret" not in result_text
    assert "authorization" not in result_text.lower()


def test_client_maps_http_errors_without_response_body_or_secret():
    with _fake_business_api() as (base_url, _state):
        settings = target.BusinessApiSettings(
            base_url=base_url,
            api_key="unit-secret-key",
            timeout_seconds=2,
            allow_insecure_local=True,
        )
        client = target.BusinessApiClient(settings)
        limited = client.query_record(record_id="limited")
        broken = client.query_record(record_id="broken")

    assert limited == {
        "ok": False,
        "status": 429,
        "error_type": "rate_limited",
        "request_id": "req-429",
        "message": "business API returned HTTP 429",
    }
    assert broken["status"] == 503
    assert broken["error_type"] == "upstream_error"
    assert "server-secret" not in json.dumps([limited, broken], ensure_ascii=False)


def test_client_handles_non_json_success_as_sanitized_text():
    with _fake_business_api() as (base_url, _state):
        settings = target.BusinessApiSettings(
            base_url=base_url,
            api_key="unit-secret-key",
            timeout_seconds=2,
            allow_insecure_local=True,
        )
        result = target.BusinessApiClient(settings).query_record(record_id="not-json")

    assert result["ok"] is True
    assert result["request_id"] == "corr-text"
    assert result["body"] == {"text": "plain text body", "content_type": "text/plain"}


def test_client_timeout_is_structured_and_secret_free(monkeypatch):
    def _raise_timeout(*_args: object, **_kwargs: object) -> None:
        raise TimeoutError("timed out with unit-secret-key")

    monkeypatch.setattr(target.urllib.request, "urlopen", _raise_timeout)
    settings = target.BusinessApiSettings(
        base_url="https://api.example.test",
        api_key="unit-secret-key",
        timeout_seconds=0.01,
    )

    result = target.BusinessApiClient(settings).get_status()

    assert result == {
        "ok": False,
        "status": 0,
        "error_type": "timeout",
        "request_id": "",
        "message": "business API request timed out",
    }
    assert "unit-secret-key" not in json.dumps(result)
