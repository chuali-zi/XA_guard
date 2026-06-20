from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

import pytest

from xa_guard.integrations.langchain import (
    XAGuardApprovalRequired,
    XAGuardCallbackHandler,
    guard_callable,
    protect_tool,
)
from xa_guard.sdk import XAGuardBlocked

CONFIG = "configs/xa-guard.docker.yaml"


class FakeBaseTool:
    name = "tool"


class EchoTool(FakeBaseTool):
    name = "echo"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def _run(self, value: str) -> str:
        self.calls.append(value)
        return f"echo:{value}"

    async def _arun(self, value: str) -> str:
        self.calls.append(value)
        return f"async:{value}"


class ExecTool(FakeBaseTool):
    name = "exec_command"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def _run(self, cmd: str) -> str:
        self.calls.append(cmd)
        return f"executed:{cmd}"


@pytest.fixture(autouse=True)
def fake_langchain(monkeypatch):
    package = types.ModuleType("langchain_core")
    tools = types.ModuleType("langchain_core.tools")
    tools.BaseTool = FakeBaseTool
    package.tools = tools
    monkeypatch.setitem(sys.modules, "langchain_core", package)
    monkeypatch.setitem(sys.modules, "langchain_core.tools", tools)


def test_module_and_callback_are_static_without_real_langchain():
    callback = XAGuardCallbackHandler()
    callback.on_tool_start({"name": "echo"}, "hello")
    callback.on_tool_end("ok")
    callback.on_tool_error(ValueError("bad"))
    assert [event["event"] for event in callback.events] == ["tool_start", "tool_end", "tool_error"]


def test_protect_tool_allows_and_audits(tmp_path: Path):
    tool = EchoTool()
    protected = protect_tool(tool, config_path=CONFIG, audit_dir=str(tmp_path / "audit"), user_role="ops")
    assert protected._run("hello") == "echo:hello"
    assert asyncio.run(protected._arun("async")) == "async:async"
    assert tool.calls == ["hello", "async"]
    assert protected.xa_guard_protected is True
    assert (tmp_path / "audit" / "audit.jsonl").exists()


def test_protect_tool_denies_before_original_call(tmp_path: Path):
    tool = ExecTool()
    protected = protect_tool(tool, config_path=CONFIG, audit_dir=str(tmp_path / "audit"), user_role="ops")
    with pytest.raises(XAGuardBlocked) as caught:
        protected._run("rm -rf /")
    assert caught.value.decision.value == "deny"
    assert tool.calls == []


def test_approval_can_resume_exact_tool_call(tmp_path: Path):
    tool = ExecTool()
    protected = protect_tool(tool, config_path=CONFIG, audit_dir=str(tmp_path / "audit"), user_role="ops")
    with pytest.raises(XAGuardApprovalRequired) as caught:
        protected._run("whoami")
    assert tool.calls == []
    assert caught.value.request.approve_sync(approver="pytest", reason="approved") == "executed:whoami"
    assert tool.calls == ["whoami"]
    with pytest.raises(RuntimeError, match="already been resolved"):
        caught.value.request.approve_sync(approver="pytest")


def test_approval_can_be_denied_without_calling_tool(tmp_path: Path):
    tool = ExecTool()
    protected = protect_tool(tool, config_path=CONFIG, audit_dir=str(tmp_path / "audit"), user_role="ops")
    with pytest.raises(XAGuardApprovalRequired) as caught:
        protected._run("whoami")
    caught.value.request.deny_sync(approver="pytest", reason="no")
    assert tool.calls == []
    assert caught.value.request.ctx.final_decision.value == "deny"
    assert caught.value.request.ctx.final_reason == "hitl_rejected: no"


def test_guard_callable_forces_preflight_before_agent_call(tmp_path: Path):
    calls = []

    def agent(payload):
        calls.append(payload)
        return "ran"

    guarded = guard_callable(
        agent, tool_name="exec_command", config_path=CONFIG, audit_dir=str(tmp_path / "audit")
    )
    with pytest.raises(XAGuardBlocked):
        guarded({"cmd": "rm -rf /"})
    assert calls == []
