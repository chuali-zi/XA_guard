from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from xa_guard.integrations.langchain import protect_tool
from xa_guard.sdk import XAGuardBlocked

CONFIG = "configs/xa-guard.docker.yaml"

tools = pytest.importorskip("langchain_core.tools")


class EchoTool(tools.BaseTool):
    name: str = "echo"
    description: str = "Echo input"
    calls: list[str] = []

    def _run(self, value: str) -> str:
        self.calls.append(value)
        return f"echo:{value}"

    async def _arun(self, value: str) -> str:
        self.calls.append(value)
        return f"async:{value}"


class ExecTool(tools.BaseTool):
    name: str = "exec_command"
    description: str = "Execute command"
    calls: list[str] = []

    def _run(self, cmd: str) -> str:
        self.calls.append(cmd)
        return "executed"


def test_protect_tool_allows_green_langchain_tool(tmp_path: Path):
    tool = EchoTool()
    protected = protect_tool(tool, config_path=CONFIG, audit_dir=str(tmp_path / "audit"))

    assert protected._run("hello") == "echo:hello"
    assert tool.calls == ["hello"]
    assert (tmp_path / "audit" / "audit.jsonl").exists()


def test_protect_tool_blocks_before_original_langchain_tool(tmp_path: Path):
    tool = ExecTool()
    protected = protect_tool(tool, config_path=CONFIG, audit_dir=str(tmp_path / "audit"))

    with pytest.raises(XAGuardBlocked):
        protected._run("rm -rf /")

    assert tool.calls == []
    assert (tmp_path / "audit" / "audit.jsonl").exists()


def test_protect_tool_supports_async_langchain_tool(tmp_path: Path):
    tool = EchoTool()
    protected = protect_tool(tool, config_path=CONFIG, audit_dir=str(tmp_path / "audit_async"))

    assert asyncio.run(protected._arun("hello")) == "async:hello"
    assert tool.calls == ["hello"]
