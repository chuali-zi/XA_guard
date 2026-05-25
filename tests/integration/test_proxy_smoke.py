"""proxy 烟雾测试 —— 验证 DownstreamRouter + Pipeline 端到端。

策略：用 tests/integration/_fixture_echo_server.py 作为下游 stdio MCP server。
- benign call：echo("hello") → pipeline allow → router 返回 CallToolResult.
- malicious call：exec_command(cmd="rm -rf /") → gate1 DENY → 不调下游。
- stop()：优雅关闭无异常。
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from xa_guard.config import DownstreamSpec, XAGuardConfig
from xa_guard.gates.gate1_input import Gate1Input
from xa_guard.gates.gate2_plan import Gate2Plan
from xa_guard.gates.gate3_policy import Gate3Policy
from xa_guard.gates.gate4_taint import Gate4Taint
from xa_guard.gates.gate5_sandbox import Gate5Sandbox
from xa_guard.gates.gate6_audit import Gate6Audit
from xa_guard.pipeline import Pipeline
from xa_guard.proxy.downstream import DownstreamRouter
from xa_guard.types import GateContext, InputSource

_FIXTURE = Path(__file__).parent / "_fixture_echo_server.py"


def _build_pipeline() -> Pipeline:
    cfg = XAGuardConfig()
    return Pipeline(
        gate1=Gate1Input(cfg.gate("gate1")),
        gate2=Gate2Plan(cfg.gate("gate2")),
        gate3=Gate3Policy(cfg.gate("gate3")),
        gate4=Gate4Taint(cfg.gate("gate4")),
        gate5=Gate5Sandbox(cfg.gate("gate5")),
        gate6=Gate6Audit(cfg.gate("gate6")),
        cfg=cfg,
    )


def _spec() -> DownstreamSpec:
    return DownstreamSpec(
        name="echo-fixture",
        command=[sys.executable, str(_FIXTURE)],
        transport="stdio",
    )


async def _scenario() -> dict:
    router = DownstreamRouter([_spec()])
    await router.start()
    try:
        tools = router.list_tools()
        assert tools, "list_tools returned empty"
        tool_names = {t["name"] for t in tools}
        assert "echo" in tool_names
        assert "exec_command" in tool_names

        pipeline = _build_pipeline()

        # benign call —— pipeline 应放行，下游被实际调用
        benign_ctx = GateContext(
            tool_name="echo",
            arguments={"text": "hello"},
            input_sources=[InputSource.USER],
        )
        benign_result = await pipeline.run(benign_ctx, router.call_tool)

        # malicious call —— gate1 检测到 "rm -rf"，DENY，不应触达下游
        evil_ctx = GateContext(
            tool_name="exec_command",
            arguments={"cmd": "rm -rf /var"},
            input_sources=[InputSource.USER],
        )
        evil_result = await pipeline.run(evil_ctx, router.call_tool)

        return {
            "tools": tools,
            "benign_allowed": benign_result.allowed,
            "benign_tool_result": benign_result.tool_result,
            "evil_allowed": evil_result.allowed,
            "evil_reason": evil_result.final_reason,
            "evil_rule_hits": list(evil_ctx.rule_hits),
        }
    finally:
        await router.stop()


def test_proxy_smoke():
    if not _FIXTURE.exists():
        pytest.skip("fixture echo server missing")
    out = asyncio.run(_scenario())

    # 1) 工具列表非空且至少包含 echo
    assert any(t["name"] == "echo" for t in out["tools"])

    # 2) benign 放行 & 下游返回有内容
    assert out["benign_allowed"] is True
    assert out["benign_tool_result"] is not None

    # 3) 危险调用被关卡 1 拦截
    assert out["evil_allowed"] is False
    assert "gate1_input" in out["evil_reason"] or "shell_dangerous" in out["evil_reason"]


def test_downstream_stop_idempotent():
    """stop() 调用两次不应抛异常（即便 start 失败也应安全）。"""

    async def run() -> None:
        router = DownstreamRouter([])
        await router.start()  # 空列表
        await router.stop()
        await router.stop()

    asyncio.run(run())
