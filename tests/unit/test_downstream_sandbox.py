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
