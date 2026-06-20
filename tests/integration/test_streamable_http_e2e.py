from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx
import mcp.types as mtypes
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from xa_guard.audit.merkle import ChainStore
from xa_guard.config import DownstreamSpec, GateConfig, XAGuardConfig
from xa_guard.gates.gate1_input import Gate1Input
from xa_guard.gates.gate2_plan import Gate2Plan
from xa_guard.gates.gate3_policy import Gate3Policy
from xa_guard.gates.gate4_taint import Gate4Taint
from xa_guard.gates.gate5_sandbox import Gate5Sandbox
from xa_guard.gates.gate6_audit import Gate6Audit
from xa_guard.pipeline import Pipeline
from xa_guard.proxy.downstream import DownstreamRouter
from xa_guard.proxy.upstream import _build_streamable_http_asgi_app


_FIXTURE = Path(__file__).parent / "_fixture_e2e_server.py"


def _pipeline(audit_dir: Path) -> Pipeline:
    cfg = XAGuardConfig()
    return Pipeline(
        gate1=Gate1Input(cfg.gate("gate1")),
        gate2=Gate2Plan(cfg.gate("gate2")),
        gate3=Gate3Policy(cfg.gate("gate3")),
        gate4=Gate4Taint(cfg.gate("gate4")),
        gate5=Gate5Sandbox(cfg.gate("gate5")),
        gate6=Gate6Audit(GateConfig(options={"audit_dir": str(audit_dir)})),
        cfg=cfg,
    )


def _text(result: mtypes.CallToolResult) -> str:
    return "".join(
        block.text for block in (result.content or []) if isinstance(block, mtypes.TextContent)
    )


def _audit_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


async def _scenario(tmp_path: Path) -> dict:
    router = DownstreamRouter(
        [DownstreamSpec(name="e2e", command=[sys.executable, str(_FIXTURE)], transport="stdio")]
    )
    await router.start()
    app = _build_streamable_http_asgi_app(
        _pipeline(tmp_path),
        router,
        host="testserver",
        port=80,
        session_idle_timeout_seconds=30,
    )
    transport = httpx.ASGITransport(app=app)

    def client_factory(headers=None, timeout=None, auth=None):
        return httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            headers=headers,
            timeout=timeout,
            auth=auth,
        )

    ready = 0
    ready_lock = asyncio.Lock()
    all_ready = asyncio.Event()
    release = asyncio.Event()

    async def one_client(index: int) -> dict:
        nonlocal ready
        async with client_factory() as http_client:
            async with streamable_http_client(
                "http://testserver/mcp",
                http_client=http_client,
            ) as (read_stream, write_stream, get_session_id):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    session_id = get_session_id()
                    tools = await session.list_tools()
                    async with ready_lock:
                        ready += 1
                        if ready == 4:
                            all_ready.set()
                    await release.wait()
                    marker = f"session-{index}-request"
                    result = await session.call_tool("echo", {"marker": marker})
                    return {
                        "session_id": session_id,
                        "tool_names": {tool.name for tool in tools.tools},
                        "result": json.loads(_text(result).removeprefix("e2e:")),
                        "expected_marker": marker,
                    }

    try:
        async with app.router.lifespan_context(app):
            tasks = [asyncio.create_task(one_client(index)) for index in range(4)]
            await asyncio.wait_for(all_ready.wait(), timeout=10)
            async with client_factory() as client:
                health_during = (await client.get("/healthz")).json()
                invalid = await client.post(
                    "/mcp",
                    headers={
                        "Mcp-Session-Id": "does-not-exist",
                        "Accept": "application/json, text/event-stream",
                    },
                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                )
            release.set()
            results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=20)
            async with client_factory() as client:
                for _ in range(20):
                    health_after = (await client.get("/healthz")).json()
                    if health_after["active_sessions"] == 0:
                        break
                    await asyncio.sleep(0.05)
        return {
            "results": results,
            "health_during": health_during,
            "health_after": health_after,
            "invalid_status": invalid.status_code,
            "audit_path": tmp_path / "audit.jsonl",
        }
    finally:
        await router.stop()


def test_streamable_http_stateful_sessions_are_isolated_and_reclaimed(tmp_path):
    out = asyncio.run(_scenario(tmp_path))
    results = out["results"]
    session_ids = [item["session_id"] for item in results]

    assert all(session_ids)
    assert len(set(session_ids)) == 4
    assert out["health_during"]["session_mode"] == "stateful"
    assert out["health_during"]["active_sessions"] == 4
    assert out["health_after"]["active_sessions"] == 0
    assert out["invalid_status"] == 404
    for item in results:
        assert "echo" in item["tool_names"]
        assert item["result"]["args"]["marker"] == item["expected_marker"]

    records = _audit_records(out["audit_path"])
    assert len(records) == 4
    assert len({record["trace_id"] for record in records}) == 4
    assert {record["gen_ai.decision.final"] for record in records} == {"allow"}
    assert {record["gen_ai.tool.name"] for record in records} == {"echo"}
    ok, bad_line = ChainStore(out["audit_path"], algo="sha256").verify()
    assert ok, f"audit chain broken at line {bad_line}"
