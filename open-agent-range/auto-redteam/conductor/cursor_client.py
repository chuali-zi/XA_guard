"""cursor_client — Cursor Cloud Agents REST API 薄客户端。

只用标准库（urllib），便于离线测试用 http.server 打桩。端点契约见
../docs/CURSOR-API-INTEGRATION.md。密钥只从环境读，绝不落盘。
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator


class CursorAPIError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"Cursor API {status}: {body[:400]}")
        self.status = status
        self.body = body


@dataclass
class CursorClient:
    api_key: str
    base_url: str = "https://api.cursor.com"
    timeout_s: float = 60.0
    max_retries: int = 4
    _sleep: Callable[[float], None] = field(default=time.sleep, repr=False)

    # ---- low-level ------------------------------------------------------
    def _url(self, path: str) -> str:
        return f"{self.base_url.rstrip('/')}{path}"

    def _request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        *,
        headers: dict | None = None,
        raw_url: str | None = None,
    ) -> tuple[int, bytes, dict]:
        url = raw_url or self._url(path)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        hdrs = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if headers:
            hdrs.update(headers)
        attempt = 0
        while True:
            attempt += 1
            req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                    return resp.status, resp.read(), dict(resp.headers)
            except urllib.error.HTTPError as exc:
                payload = exc.read()
                if exc.code in (429, 500, 502, 503, 504) and attempt <= self.max_retries:
                    self._sleep(min(2 ** attempt, 30))
                    continue
                raise CursorAPIError(exc.code, payload.decode("utf-8", "replace"))
            except urllib.error.URLError:
                if attempt <= self.max_retries:
                    self._sleep(min(2 ** attempt, 30))
                    continue
                raise

    def _json(self, method: str, path: str, body: dict | None = None) -> dict:
        status, raw, _ = self._request(method, path, body)
        if status >= 400:
            raise CursorAPIError(status, raw.decode("utf-8", "replace"))
        return json.loads(raw.decode("utf-8")) if raw else {}

    # ---- metadata -------------------------------------------------------
    def get_me(self) -> dict:
        return self._json("GET", "/v1/me")

    def list_models(self) -> dict:
        return self._json("GET", "/v1/models")

    # ---- agents / runs --------------------------------------------------
    def create_agent(
        self,
        *,
        prompt_text: str,
        repo_url: str,
        starting_ref: str,
        model_id: str | None = None,
        env_vars: list[dict] | None = None,
        mcp_servers: list[dict] | None = None,
        auto_create_pr: bool = False,
        name: str | None = None,
    ) -> dict:
        body: dict[str, Any] = {
            "prompt": {"text": prompt_text},
            "repos": [{"url": repo_url, "startingRef": starting_ref}],
            "autoCreatePR": auto_create_pr,
        }
        if model_id:
            body["model"] = {"id": model_id}
        if env_vars:
            body["envVars"] = env_vars
        if mcp_servers:
            body["mcpServers"] = mcp_servers
        if name:
            body["name"] = name
        return self._json("POST", "/v1/agents", body)

    def create_run(self, agent_id: str, prompt_text: str) -> dict:
        return self._json("POST", f"/v1/agents/{agent_id}/runs", {"prompt": {"text": prompt_text}})

    def get_run(self, agent_id: str, run_id: str) -> dict:
        return self._json("GET", f"/v1/agents/{agent_id}/runs/{run_id}")

    def cancel_run(self, agent_id: str, run_id: str) -> dict:
        return self._json("POST", f"/v1/agents/{agent_id}/runs/{run_id}/cancel")

    def get_usage(self, agent_id: str, run_id: str | None = None) -> dict:
        suffix = f"?runId={run_id}" if run_id else ""
        return self._json("GET", f"/v1/agents/{agent_id}/usage{suffix}")

    def archive_agent(self, agent_id: str) -> dict:
        return self._json("POST", f"/v1/agents/{agent_id}/archive")

    def delete_agent(self, agent_id: str) -> dict:
        return self._json("DELETE", f"/v1/agents/{agent_id}")

    # ---- streaming ------------------------------------------------------
    def stream_run(
        self,
        agent_id: str,
        run_id: str,
        *,
        last_event_id: str | None = None,
    ) -> Iterator[dict]:
        """逐个 yield SSE 事件 {'event','data','id'}。断线由调用方带 last_event_id 重连。"""
        url = self._url(f"/v1/agents/{agent_id}/runs/{run_id}/stream")
        hdrs = {"Authorization": f"Bearer {self.api_key}", "Accept": "text/event-stream"}
        if last_event_id:
            hdrs["Last-Event-ID"] = last_event_id
        req = urllib.request.Request(url, method="GET", headers=hdrs)
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            event: dict[str, str] = {}
            for raw_line in resp:
                line = raw_line.decode("utf-8", "replace").rstrip("\n").rstrip("\r")
                if line == "":
                    if event:
                        yield {
                            "event": event.get("event", "message"),
                            "data": event.get("data", ""),
                            "id": event.get("id"),
                        }
                        event = {}
                    continue
                if line.startswith(":"):
                    continue
                key, _, value = line.partition(":")
                value = value[1:] if value.startswith(" ") else value
                if key in ("event", "id"):
                    event[key] = value
                elif key == "data":
                    event["data"] = (event.get("data", "") + value) if "data" in event else value

    # ---- artifacts ------------------------------------------------------
    def list_artifacts(self, agent_id: str) -> list[dict]:
        return self._json("GET", f"/v1/agents/{agent_id}/artifacts").get("items", [])

    def download_artifact(self, agent_id: str, path: str) -> bytes:
        """列举返回预签名 URL；再拉实际字节。测试用的 fake server 直接回字节亦可。"""
        import urllib.parse

        q = urllib.parse.urlencode({"path": path})
        status, raw, _ = self._request("GET", f"/v1/agents/{agent_id}/artifacts/download?{q}")
        if status >= 400:
            raise CursorAPIError(status, raw.decode("utf-8", "replace"))
        # 若返回的是 JSON {url: presigned}，跟进下载；否则视为直接字节。
        try:
            doc = json.loads(raw.decode("utf-8"))
            presigned = doc.get("url") or doc.get("downloadUrl")
        except (ValueError, UnicodeDecodeError):
            presigned = None
        if presigned:
            status2, raw2, _ = self._request("GET", "", raw_url=presigned, headers={"Accept": "*/*"})
            if status2 >= 400:
                raise CursorAPIError(status2, "artifact download failed")
            return raw2
        return raw
