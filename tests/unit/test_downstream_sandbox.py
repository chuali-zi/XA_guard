from __future__ import annotations

import asyncio

from xa_guard.config import DownstreamSpec
from xa_guard.proxy.downstream import DownstreamRouter
from xa_guard.types import Decision, GateContext, GateResult


class _NativeSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def call_tool(self, name: str, arguments: dict):
        self.calls.append((name, arguments))
        return {"via": "native"}


def _ctx_with_gate5(mode: str) -> GateContext:
    ctx = GateContext(tool_name="echo", arguments={"value": "hello"})
    ctx.append(
        GateResult(
            gate_name="gate5_sandbox",
            decision=Decision.ALLOW,
            metadata={
                "sandbox_mode": mode,
                "sandbox_enforced": mode != "native",
                "docker_image": "xa-guard/sandbox:test",
                "runtime": "runsc",
                "network_disabled": True,
                "readonly_rootfs": True,
            },
        )
    )
    return ctx


def test_downstream_native_mode_uses_persistent_session():
    spec = DownstreamSpec(name="fixture", command=["python", "-m", "demo.targets.ops_target"])
    native = _NativeSession()
    router = DownstreamRouter([spec])
    router.tools_by_name["echo"] = (spec, native)  # type: ignore[assignment]

    result = asyncio.run(router.call_tool(_ctx_with_gate5("native")))

    assert result == {"via": "native"}
    assert native.calls == [("echo", {"value": "hello"})]


def test_downstream_docker_mode_uses_sandboxed_stdio_session(monkeypatch):
    spec = DownstreamSpec(name="fixture", command=["python", "-m", "demo.targets.ops_target"])
    native = _NativeSession()
    router = DownstreamRouter([spec])
    router.tools_by_name["echo"] = (spec, native)  # type: ignore[assignment]
    sandbox_calls = []

    async def fake_sandboxed_call(captured_spec, ctx, policy):
        sandbox_calls.append((captured_spec, ctx.tool_name, dict(ctx.arguments), policy.mode))
        return {"via": "sandbox", "mode": policy.mode}

    monkeypatch.setattr(router, "_call_tool_sandboxed", fake_sandboxed_call)

    result = asyncio.run(router.call_tool(_ctx_with_gate5("docker")))

    assert result == {"via": "sandbox", "mode": "docker"}
    assert native.calls == []
    assert sandbox_calls == [(spec, "echo", {"value": "hello"}, "docker")]


def test_downstream_gvisor_mode_uses_sandboxed_stdio_session(monkeypatch):
    spec = DownstreamSpec(name="fixture", command=["python", "-m", "demo.targets.ops_target"])
    native = _NativeSession()
    router = DownstreamRouter([spec])
    router.tools_by_name["echo"] = (spec, native)  # type: ignore[assignment]
    sandbox_modes = []

    async def fake_sandboxed_call(captured_spec, ctx, policy):
        sandbox_modes.append(policy.mode)
        return {"via": "sandbox", "mode": policy.mode, "runtime": policy.runtime}

    monkeypatch.setattr(router, "_call_tool_sandboxed", fake_sandboxed_call)

    result = asyncio.run(router.call_tool(_ctx_with_gate5("docker_gvisor")))

    assert result == {"via": "sandbox", "mode": "docker_gvisor", "runtime": "runsc"}
    assert native.calls == []
    assert sandbox_modes == ["docker_gvisor"]


def test_downstream_static_manifest_does_not_start_native_session():
    spec = DownstreamSpec(
        name="fixture",
        command=["python", "-m", "demo.targets.ops_target"],
        tools=[
            {
                "name": "echo",
                "description": "Echo a value",
                "inputSchema": {"type": "object", "properties": {"value": {"type": "string"}}},
            }
        ],
    )
    router = DownstreamRouter([spec])

    asyncio.run(router.start())
    try:
        assert router.list_tools() == [
            {
                "name": "echo",
                "description": "Echo a value",
                "inputSchema": {"type": "object", "properties": {"value": {"type": "string"}}},
            }
        ]
        assert router._sessions == {}
        assert router.tools_by_name["echo"][1] is None
    finally:
        asyncio.run(router.stop())


def test_downstream_static_manifest_requires_sandbox_for_call():
    spec = DownstreamSpec(
        name="fixture",
        command=["python", "-m", "demo.targets.ops_target"],
        tools=[{"name": "echo", "description": "Echo a value", "inputSchema": {"type": "object"}}],
    )
    router = DownstreamRouter([spec])
    asyncio.run(router.start())
    try:
        try:
            asyncio.run(router.call_tool(_ctx_with_gate5("native")))
        except RuntimeError as exc:
            assert "static tool discovery" in str(exc)
        else:
            raise AssertionError("static manifest native call should fail closed")
    finally:
        asyncio.run(router.stop())


def test_downstream_static_manifest_sandboxed_call(monkeypatch):
    spec = DownstreamSpec(
        name="fixture",
        command=["python", "-m", "demo.targets.ops_target"],
        tools=[{"name": "echo", "description": "Echo a value", "inputSchema": {"type": "object"}}],
    )
    router = DownstreamRouter([spec])
    sandbox_calls = []

    async def fake_sandboxed_call(captured_spec, ctx, policy):
        sandbox_calls.append((captured_spec, ctx.tool_name, policy.mode))
        return {"via": "sandbox"}

    monkeypatch.setattr(router, "_call_tool_sandboxed", fake_sandboxed_call)

    asyncio.run(router.start())
    try:
        result = asyncio.run(router.call_tool(_ctx_with_gate5("docker")))
    finally:
        asyncio.run(router.stop())

    assert result == {"via": "sandbox"}
    assert sandbox_calls == [(spec, "echo", "docker")]
