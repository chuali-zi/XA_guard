"""MCP 端到端 harness —— 真 JSON-RPC tools/call 穿过上游 guard server。

与 test_proxy_smoke 的区别：smoke 直接调 `pipeline.run(ctx, executor)`，
**绕过了上游 MCP server 协议层**。本 harness 用 mcp 进程内内存 transport
把一个真实 ClientSession（扮演 LLM 客户端）接到 `proxy.upstream._build_app`
构造的 guard Server 上，发起真实 `tools/call` JSON-RPC，覆盖：

1. allow   —— echo：放行，下游被调用一次，返回下游内容。
2. deny    —— exec_command(rm -rf)：Gate1 拦截，下游 0 次调用。
3. approve —— grant_permission：Gate2 REQUIRE_APPROVAL，客户端 elicitation
              回 approve=true → 下游被调用一次，返回下游内容。
4. reject  —— grant_permission：客户端 elicitation 回 decline → 下游 0 次调用。

每个场景都断言：返回内容、下游调用次数 delta、以及 Gate6 审计 JSONL
新增的记录数与 final decision。最后整体校验审计哈希链完好。
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import mcp.types as mtypes
import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import ElicitResult

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
from xa_guard.proxy.upstream import _build_app
from xa_guard.types import GateContext

_FIXTURE = Path(__file__).parent / "_fixture_e2e_server.py"


class CountingRouter(DownstreamRouter):
    """包装 DownstreamRouter，统计真正触达下游的 call_tool 次数。"""

    def __init__(self, specs: list[DownstreamSpec]) -> None:
        super().__init__(specs)
        self.downstream_calls = 0

    async def call_tool(self, ctx: GateContext):
        self.downstream_calls += 1
        return await super().call_tool(ctx)


def _build_pipeline(audit_dir: Path) -> tuple[Pipeline, Gate6Audit]:
    cfg = XAGuardConfig()
    gate6 = Gate6Audit(GateConfig(options={"audit_dir": str(audit_dir)}))
    pipeline = Pipeline(
        gate1=Gate1Input(cfg.gate("gate1")),
        gate2=Gate2Plan(cfg.gate("gate2")),
        gate3=Gate3Policy(cfg.gate("gate3")),
        gate4=Gate4Taint(cfg.gate("gate4")),
        gate5=Gate5Sandbox(cfg.gate("gate5")),
        gate6=gate6,
        cfg=cfg,
    )
    return pipeline, gate6


def _text(result: mtypes.CallToolResult) -> str:
    return "".join(
        b.text for b in (result.content or []) if isinstance(b, mtypes.TextContent)
    )


def _read_audit(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


async def _approve_cb(_context, _params) -> ElicitResult:
    return ElicitResult(action="accept", content={"approve": True, "reason": "e2e-approve"})


async def _reject_cb(_context, _params) -> ElicitResult:
    return ElicitResult(action="decline")


async def _call(server, name: str, args: dict, elicitation_callback=None) -> mtypes.CallToolResult:
    async with create_connected_server_and_client_session(
        server, elicitation_callback=elicitation_callback
    ) as client:
        return await client.call_tool(name, args)


async def _scenario(tmp_path: Path) -> dict:
    audit_path = tmp_path / "audit.jsonl"
    router = CountingRouter(
        [DownstreamSpec(name="e2e", command=[sys.executable, str(_FIXTURE)], transport="stdio")]
    )
    await router.start()
    try:
        pipeline, _gate6 = _build_pipeline(tmp_path)
        server = _build_app(pipeline, router)

        out: dict = {}

        # ---- 1) allow: echo ----
        before = router.downstream_calls
        before_n = len(_read_audit(audit_path))
        r = await _call(server, "echo", {"text": "hello"})
        out["allow"] = {
            "text": _text(r),
            "is_error": bool(r.isError),
            "downstream_delta": router.downstream_calls - before,
            "audit_delta": _read_audit(audit_path)[before_n:],
        }

        # ---- 2) deny: exec_command rm -rf ----
        before = router.downstream_calls
        before_n = len(_read_audit(audit_path))
        r = await _call(server, "exec_command", {"cmd": "rm -rf /var"})
        out["deny"] = {
            "text": _text(r),
            "downstream_delta": router.downstream_calls - before,
            "audit_delta": _read_audit(audit_path)[before_n:],
        }

        # ---- 3) approve: grant_permission + elicitation approve ----
        before = router.downstream_calls
        before_n = len(_read_audit(audit_path))
        r = await _call(server, "grant_permission", {"user": "alice"}, _approve_cb)
        out["approve"] = {
            "text": _text(r),
            "downstream_delta": router.downstream_calls - before,
            "audit_delta": _read_audit(audit_path)[before_n:],
        }

        # ---- 4) reject: grant_permission + elicitation decline ----
        before = router.downstream_calls
        before_n = len(_read_audit(audit_path))
        r = await _call(server, "grant_permission", {"user": "bob"}, _reject_cb)
        out["reject"] = {
            "text": _text(r),
            "downstream_delta": router.downstream_calls - before,
            "audit_delta": _read_audit(audit_path)[before_n:],
        }

        out["audit_path"] = audit_path
        return out
    finally:
        await router.stop()


def _decisions(records: list[dict]) -> list[str]:
    return [r.get("gen_ai.decision.final") for r in records]


def test_mcp_e2e_harness(tmp_path):
    if not _FIXTURE.exists():
        pytest.skip("e2e fixture server missing")
    out = asyncio.run(_scenario(tmp_path))

    # 1) allow: 放行，下游调用一次，返回下游真实内容，审计一条 allow
    allow = out["allow"]
    assert allow["downstream_delta"] == 1
    assert "e2e:" in allow["text"]
    assert "alice" not in allow["text"]  # 不串场景
    assert _decisions(allow["audit_delta"]) == ["allow"]
    assert allow["audit_delta"][0]["gen_ai.tool.name"] == "echo"

    # 2) deny: Gate1 拦截，下游 0 次，返回拦截提示，审计一条 deny
    deny = out["deny"]
    assert deny["downstream_delta"] == 0
    assert "拦截" in deny["text"]
    assert _decisions(deny["audit_delta"]) == ["deny"]

    # 3) approve: 下游被调用一次，返回下游内容；审计 require_approval -> allow 两条
    approve = out["approve"]
    assert approve["downstream_delta"] == 1
    assert "e2e:" in approve["text"]
    assert "alice" in approve["text"]
    assert _decisions(approve["audit_delta"]) == ["require_approval", "allow"]

    # 4) reject: 下游 0 次，返回拒绝提示；审计一条 require_approval
    reject = out["reject"]
    assert reject["downstream_delta"] == 0
    assert "拒绝" in reject["text"]
    assert _decisions(reject["audit_delta"]) == ["require_approval"]

    # 5) 审计哈希链整体可验
    chain = ChainStore(out["audit_path"], algo="sha256")
    ok, bad_line = chain.verify()
    assert ok, f"audit chain broken at line {bad_line}"
    assert len(_read_audit(out["audit_path"])) == 5
