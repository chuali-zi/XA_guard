from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import mcp.types as mtypes
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import ElicitResult

from xa_guard.config import DownstreamSpec, GateConfig, GovernanceConfig
from xa_guard.gates.base import Gate, GateStage
from xa_guard.gates.gate6_audit import Gate6Audit
from xa_guard.governance import GovernanceEnforcer
from xa_guard.pipeline import Pipeline
from xa_guard.proxy.downstream import DownstreamRouter
from xa_guard.proxy.upstream import _build_app
from xa_guard.types import Decision, GateContext, GateResult


_FIXTURE = Path(__file__).parent / "_fixture_e2e_server.py"
_REGISTRY = Path("configs/governance.demo.yaml")


class _AllowGate(Gate):
    supported_stages = (GateStage.INBOUND, GateStage.OUTBOUND)

    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name

    def evaluate(self, ctx: GateContext, stage: GateStage = GateStage.INBOUND) -> GateResult:
        return GateResult(gate_name=self.name, decision=Decision.ALLOW)


class CountingRouter(DownstreamRouter):
    def __init__(self, specs: list[DownstreamSpec]) -> None:
        super().__init__(specs)
        self.downstream_calls = 0

    async def call_tool(self, ctx: GateContext):
        self.downstream_calls += 1
        return await super().call_tool(ctx)


def _pipeline(tmp_path: Path) -> Pipeline:
    return Pipeline(
        gate1=_AllowGate("gate1"),
        gate2=_AllowGate("gate2"),
        gate3=_AllowGate("gate3"),
        gate4=_AllowGate("gate4"),
        gate5=_AllowGate("gate5"),
        gate6=Gate6Audit(GateConfig(options={"audit_dir": str(tmp_path)})),
        governance=GovernanceEnforcer(
            GovernanceConfig(enabled=True, registry_file=str(_REGISTRY), default_tenant="acme-corp")
        ),
    )


def _text(result: mtypes.CallToolResult) -> str:
    return "".join(block.text for block in result.content or [] if isinstance(block, mtypes.TextContent))


async def _approve_cb(_context, _params) -> ElicitResult:
    return ElicitResult(action="accept", content={"approve": True, "reason": "governance-ok"})


async def _call(server, name: str, args: dict, elicitation_callback=None) -> mtypes.CallToolResult:
    async with create_connected_server_and_client_session(
        server, elicitation_callback=elicitation_callback
    ) as client:
        return await client.call_tool(name, args)


async def _scenario(tmp_path: Path) -> dict:
    router = CountingRouter(
        [DownstreamSpec(name="e2e", command=[sys.executable, str(_FIXTURE)], transport="stdio")]
    )
    await router.start()
    try:
        server = _build_app(_pipeline(tmp_path), router)

        denied = await _call(
            server,
            "echo",
            {
                "text": "show every employee payroll",
                "_xa_guard": {
                    "tenant_id": "acme-corp",
                    "human_principal": "bob.dev@acme.local",
                    "agent_id": "general-office-agent",
                    "data_domain": "payroll",
                    "resource_owner": "all",
                    "task_id": "task-payroll-deny",
                    "cost_estimate_usd": 0.25,
                    "output_estimate": "payroll export",
                    "capability_token": {
                        "scope": "payroll:read",
                        "ttl": "5m",
                        "token": "raw-secret-token",
                        "signature": "raw-signature",
                    },
                },
            },
        )
        denied_calls = router.downstream_calls

        approved = await _call(
            server,
            "echo",
            {
                "text": "summarize Bob's payroll row for HR review",
                "_xa_guard": {
                    "tenant_id": "acme-corp",
                    "human_principal": "alice.hr@acme.local",
                    "agent_id": "hr-assistant",
                    "data_domain": "payroll",
                    "resource_owner": "bob.dev@acme.local",
                    "task_id": "task-payroll-approve",
                    "cost_estimate_usd": 0.30,
                },
            },
            _approve_cb,
        )
        records = [
            json.loads(line)
            for line in (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        return {
            "denied_text": _text(denied),
            "approved_text": _text(approved),
            "downstream_calls_after_denied": denied_calls,
            "downstream_calls_final": router.downstream_calls,
            "records": records,
        }
    finally:
        await router.stop()


def test_governance_mcp_envelope_strips_metadata_and_audits_identity(tmp_path):
    out = asyncio.run(_scenario(tmp_path))

    assert "拦截" in out["denied_text"]
    assert out["downstream_calls_after_denied"] == 0
    assert out["downstream_calls_final"] == 1
    assert "e2e:" in out["approved_text"]
    assert "_xa_guard" not in out["approved_text"]

    denied, pending, approved = out["records"]
    assert denied["gen_ai.decision.final"] == "deny"
    assert denied["gen_ai.tool.parameters"] == {"text": "show every employee payroll"}
    assert denied["gen_ai.governance.human_principal"] == "bob.dev@acme.local"
    assert denied["gen_ai.governance.agent_id"] == "general-office-agent"
    assert denied["gen_ai.governance.data_domain"] == "payroll"
    capability = denied["gen_ai.governance.capability_token"]
    assert capability["scope"] == "payroll:read"
    assert capability["ttl"] == "5m"
    assert "token_sha256" in capability
    assert "signature_sha256" in capability
    assert "raw-secret-token" not in json.dumps(denied, ensure_ascii=False)
    assert "raw-signature" not in json.dumps(denied, ensure_ascii=False)
    assert "GOV-EMPLOYEE-DATA-DOMAIN" in denied["gen_ai.policy.hit_id"]

    assert pending["gen_ai.decision.final"] == "require_approval"
    assert "GOV-DATA-DOMAIN-APPROVAL" in pending["gen_ai.policy.hit_id"]
    assert approved["gen_ai.decision.final"] == "allow"
    assert approved["gen_ai.governance.human_principal"] == "alice.hr@acme.local"
    assert approved["gen_ai.tool.parameters"] == {"text": "summarize Bob's payroll row for HR review"}
