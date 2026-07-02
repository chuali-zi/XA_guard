from __future__ import annotations

import asyncio
import json
import sys
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import mcp.types as mtypes
import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import ElicitResult

from xa_guard.config import DownstreamSpec, GateConfig, GovernanceConfig, XAGuardConfig
from xa_guard.gates.gate1_input import Gate1Input
from xa_guard.gates.gate2_plan import Gate2Plan
from xa_guard.gates.gate3_policy import Gate3Policy
from xa_guard.gates.gate4_taint import Gate4Taint
from xa_guard.gates.gate5_sandbox import Gate5Sandbox
from xa_guard.gates.gate6_audit import Gate6Audit
from xa_guard.governance import GovernanceEnforcer
from xa_guard.pipeline import Pipeline
from xa_guard.policy.layered import LayeredPolicySource, set_global_source
from xa_guard.proxy.downstream import DownstreamRouter
from xa_guard.proxy.upstream import _build_app
from xa_guard.types import GateContext, TaintLabel

PROJECT_ROOT = Path(__file__).resolve().parents[2]
POLICY_FILE = PROJECT_ROOT / "policies/baseline/gate3_rules.yaml"
CAP_FILE = PROJECT_ROOT / "policies/baseline/gate4_capabilities.yaml"
GOV_REGISTRY = PROJECT_ROOT / "configs/governance.enterprise-static.yaml"
BUSINESS_API_KEY = "integration-secret-key"


@pytest.fixture(autouse=True)
def _isolate_layered_source():
    set_global_source(
        LayeredPolicySource(
            manifest_path="policies/baseline/manifest.yaml",
            overlay_root=None,
            project_root=PROJECT_ROOT,
        )
    )
    yield
    set_global_source(None)


@contextmanager
def _fake_business_api():
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

        def _authorized(self) -> bool:
            return self.headers.get("authorization") == f"Bearer {BUSINESS_API_KEY}"

        def do_GET(self) -> None:
            state["calls"].append(
                {
                    "method": "GET",
                    "path": self.path,
                    "authorization": self.headers.get("authorization", ""),
                }
            )
            if not self._authorized():
                self._send_json(401, {"error": "bad auth", "token": BUSINESS_API_KEY}, "req-auth")
                return
            if self.path.startswith("/status"):
                self._send_json(200, {"status": "ok", "secret": BUSINESS_API_KEY}, "req-status")
                return
            record_id = self.path.split("?", 1)[0].rsplit("/", 1)[-1]
            self._send_json(
                200,
                {
                    "record_id": record_id,
                    "summary": "business record summary",
                    "token": BUSINESS_API_KEY,
                },
                "req-record",
            )

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
            if not self._authorized():
                self._send_json(403, {"error": "forbidden", "token": BUSINESS_API_KEY}, "req-auth")
                return
            self._send_json(
                201,
                {"ticket_id": "T-900", "status": "created", "api_key": BUSINESS_API_KEY},
                "req-ticket",
            )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", state
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


class CountingRouter(DownstreamRouter):
    def __init__(self, specs: list[DownstreamSpec]) -> None:
        super().__init__(specs)
        self.downstream_calls = 0

    async def call_tool(self, ctx: GateContext):
        self.downstream_calls += 1
        return await super().call_tool(ctx)


def _configure_env(monkeypatch: pytest.MonkeyPatch, base_url: str, tmp_path: Path) -> None:
    monkeypatch.setenv("BUSINESS_API_BASE_URL", base_url)
    monkeypatch.setenv("BUSINESS_API_KEY", BUSINESS_API_KEY)
    monkeypatch.setenv("BUSINESS_API_TIMEOUT_SECONDS", "2")
    monkeypatch.setenv("BUSINESS_API_ALLOW_INSECURE_LOCAL", "true")
    monkeypatch.setenv("XA_GUARD_PENDING_APPROVAL_STORE", str(tmp_path / "pending_approvals.jsonl"))


def _pipeline(tmp_path: Path, *, governance: bool = False) -> Pipeline:
    cfg = XAGuardConfig(pending_approvals_path=str(tmp_path / "pending_approvals.jsonl"))
    gov = None
    if governance:
        gov = GovernanceEnforcer(
            GovernanceConfig(
                enabled=True,
                registry_file=str(GOV_REGISTRY),
                default_tenant="acme-corp",
            )
        )
    return Pipeline(
        gate1=Gate1Input(
            GateConfig(
                enabled=True,
                options={"patterns_file": "policies/baseline/gate1_input_patterns.yaml"},
            )
        ),
        gate2=Gate2Plan(
            GateConfig(
                enabled=True,
                options={"prefer_layered": True, "elicitation_fallback": "stdout"},
            )
        ),
        gate3=Gate3Policy(
            GateConfig(enabled=True, options={"backend": "python", "policy_file": str(POLICY_FILE)})
        ),
        gate4=Gate4Taint(
            GateConfig(enabled=True, options={"tool_capabilities_file": str(CAP_FILE)})
        ),
        gate5=Gate5Sandbox(GateConfig(enabled=False)),
        gate6=Gate6Audit(GateConfig(enabled=True, options={"audit_dir": str(tmp_path)})),
        cfg=cfg,
        governance=gov,
    )


def _router() -> CountingRouter:
    return CountingRouter(
        [
            DownstreamSpec(
                name="business_api",
                command=[sys.executable, "-m", "demo.targets.business_api_target"],
                transport="stdio",
                env_passthrough=[
                    "BUSINESS_API_BASE_URL",
                    "BUSINESS_API_KEY",
                    "BUSINESS_API_TIMEOUT_SECONDS",
                    "BUSINESS_API_ALLOW_INSECURE_LOCAL",
                ],
            )
        ]
    )


def _read_audit(tmp_path: Path) -> list[dict[str, Any]]:
    audit_path = tmp_path / "audit.jsonl"
    if not audit_path.exists():
        return []
    return [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]


def _text(result: mtypes.CallToolResult) -> str:
    return "".join(block.text for block in result.content or [] if isinstance(block, mtypes.TextContent))


async def _call(server, name: str, args: dict[str, Any], elicitation_callback=None):
    async with create_connected_server_and_client_session(
        server,
        elicitation_callback=elicitation_callback,
    ) as client:
        return await client.call_tool(name, args)


async def _approve_cb(_context, _params) -> ElicitResult:
    return ElicitResult(action="accept", content={"approve": True, "reason": "business-api-ok"})


async def _query_record_scenario(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    with _fake_business_api() as (base_url, state):
        _configure_env(monkeypatch, base_url, tmp_path)
        router = _router()
        await router.start()
        try:
            server = _build_app(_pipeline(tmp_path), router)
            result = await _call(
                server,
                "business_query_record",
                {
                    "record_id": "REC-42",
                    "tenant_id": "acme-corp",
                    "_xa_guard": {
                        "tenant_id": "acme-corp",
                        "principal_id": "bob.dev@acme.local",
                        "agent_id": "general-office-agent",
                        "data_domain": "engineering_docs",
                        "resource_owner": "bob.dev@acme.local",
                        "task_id": "business-query",
                        "cost_estimate_usd": 0.05,
                    },
                },
            )
            return {
                "text": _text(result),
                "calls": list(state["calls"]),
                "downstream_calls": router.downstream_calls,
                "records": _read_audit(tmp_path),
            }
        finally:
            await router.stop()


def test_business_query_record_mcp_success_strips_envelope_and_audits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    out = asyncio.run(_query_record_scenario(tmp_path, monkeypatch))

    assert out["downstream_calls"] == 1
    assert len(out["calls"]) == 1
    assert out["calls"][0]["method"] == "GET"
    assert out["calls"][0]["path"].startswith("/records/REC-42")
    assert "_xa_guard" not in out["calls"][0]["path"]
    assert "REC-42" in out["text"]
    assert "_xa_guard" not in out["text"]
    assert BUSINESS_API_KEY not in out["text"]

    record = out["records"][-1]
    assert record["gen_ai.tool.name"] == "business_query_record"
    assert record["gen_ai.decision.final"] == "warn"
    assert record["gen_ai.tool.parameters"] == {"record_id": "REC-42", "tenant_id": "acme-corp"}
    assert record["gen_ai.tool.result.hash"]
    assert BUSINESS_API_KEY not in json.dumps(record, ensure_ascii=False)


async def _submit_ticket_pending_scenario(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    with _fake_business_api() as (base_url, state):
        _configure_env(monkeypatch, base_url, tmp_path)
        router = _router()
        await router.start()
        try:
            server = _build_app(_pipeline(tmp_path), router)
            result = await _call(
                server,
                "business_submit_ticket",
                {
                    "title": "Need access review",
                    "description": "Please review internal ticket",
                    "priority": "high",
                },
            )
            return {
                "text": _text(result),
                "calls": list(state["calls"]),
                "downstream_calls": router.downstream_calls,
                "records": _read_audit(tmp_path),
                "ledger_text": (tmp_path / "pending_approvals.jsonl").read_text(encoding="utf-8"),
            }
        finally:
            await router.stop()


def test_business_submit_ticket_requires_approval_and_does_not_call_api_without_approval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    out = asyncio.run(_submit_ticket_pending_scenario(tmp_path, monkeypatch))

    assert "等待人工审批" in out["text"]
    assert out["downstream_calls"] == 0
    assert out["calls"] == []
    assert out["records"][-1]["gen_ai.decision.final"] == "require_approval"
    assert "XA-BUSINESS-API-WRITE-APPROVAL" in out["records"][-1]["gen_ai.policy.hit_id"]
    assert BUSINESS_API_KEY not in out["ledger_text"]
    assert BUSINESS_API_KEY not in json.dumps(out["records"], ensure_ascii=False)


async def _submit_ticket_approved_scenario(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    with _fake_business_api() as (base_url, state):
        _configure_env(monkeypatch, base_url, tmp_path)
        router = _router()
        await router.start()
        try:
            server = _build_app(_pipeline(tmp_path), router)
            result = await _call(
                server,
                "business_submit_ticket",
                {
                    "title": "Need access review",
                    "description": "Please review internal ticket",
                    "priority": "high",
                },
                _approve_cb,
            )
            return {
                "text": _text(result),
                "calls": list(state["calls"]),
                "downstream_calls": router.downstream_calls,
                "records": _read_audit(tmp_path),
            }
        finally:
            await router.stop()


def test_business_submit_ticket_approval_executes_once_and_redacts_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    out = asyncio.run(_submit_ticket_approved_scenario(tmp_path, monkeypatch))

    assert out["downstream_calls"] == 1
    assert len(out["calls"]) == 1
    assert out["calls"][0]["method"] == "POST"
    assert out["calls"][0]["path"] == "/tickets"
    assert "T-900" in out["text"]
    assert BUSINESS_API_KEY not in out["text"]
    assert [record["gen_ai.decision.final"] for record in out["records"]] == [
        "require_approval",
        "allow",
    ]
    assert out["records"][-1]["gen_ai.tool.approval.reason"] == "business-api-ok"
    assert BUSINESS_API_KEY not in json.dumps(out["records"], ensure_ascii=False)


async def _confidential_deny_scenario(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    with _fake_business_api() as (base_url, state):
        _configure_env(monkeypatch, base_url, tmp_path)
        router = _router()
        await router.start()
        try:
            pipe = _pipeline(tmp_path)
            ctx = GateContext(
                tool_name="business_query_record",
                arguments={"record_id": "REC-99"},
                taint=TaintLabel.CONFIDENTIAL,
            )
            result = await pipe.run(ctx, router.call_tool)
            return {
                "final_reason": result.final_reason,
                "calls": list(state["calls"]),
                "downstream_calls": router.downstream_calls,
                "records": _read_audit(tmp_path),
            }
        finally:
            await router.stop()


def test_confidential_taint_to_external_business_tool_denies_before_api(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    out = asyncio.run(_confidential_deny_scenario(tmp_path, monkeypatch))

    assert "gate4_taint" in out["final_reason"]
    assert out["downstream_calls"] == 0
    assert out["calls"] == []
    record = out["records"][-1]
    assert record["gen_ai.decision.final"] == "deny"
    assert record["gen_ai.data.sensitivity_level"] == "CONFIDENTIAL"
    assert "gate4_taint" in record["gen_ai.decision.final_reason"]


async def _governance_deny_scenario(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    with _fake_business_api() as (base_url, state):
        _configure_env(monkeypatch, base_url, tmp_path)
        router = _router()
        await router.start()
        try:
            server = _build_app(_pipeline(tmp_path, governance=True), router)
            result = await _call(
                server,
                "business_query_record",
                {
                    "record_id": "REC-7",
                    "_xa_guard": {
                        "tenant_id": "acme-corp",
                        "agent_id": "general-office-agent",
                        "data_domain": "engineering_docs",
                        "resource_owner": "bob.dev@acme.local",
                    },
                },
            )
            return {
                "text": _text(result),
                "calls": list(state["calls"]),
                "downstream_calls": router.downstream_calls,
                "records": _read_audit(tmp_path),
            }
        finally:
            await router.stop()


def test_governance_missing_principal_blocks_business_api_before_downstream(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    out = asyncio.run(_governance_deny_scenario(tmp_path, monkeypatch))

    assert "拦截" in out["text"]
    assert out["downstream_calls"] == 0
    assert out["calls"] == []
    record = out["records"][-1]
    assert record["gen_ai.decision.final"] == "deny"
    assert record["gen_ai.governance.decision_reason_code"] == "GOV-MISSING-PRINCIPAL"
    assert record["gen_ai.tool.parameters"] == {"record_id": "REC-7"}
