from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from xa_guard import protect
from xa_guard.sdk import XAGuardBlocked


CONFIG = "configs/xa-guard.docker.yaml"


def test_sdk_public_imports_are_available() -> None:
    from sdk import protect as legacy_protect
    from xa_guard import protect as root_protect
    from xa_guard.sdk import protect as namespaced_protect

    assert root_protect is protect
    assert namespaced_protect is protect
    assert legacy_protect is protect


def test_protect_allows_green_tool_and_calls_original(tmp_path: Path) -> None:
    calls: list[str] = []

    @protect(config_path=CONFIG, tool_name="echo", audit_dir=str(tmp_path / "audit"))
    def echo(message: str) -> str:
        calls.append(message)
        return f"echo:{message}"

    assert echo("hello") == "echo:hello"
    assert calls == ["hello"]
    assert (tmp_path / "audit" / "audit.jsonl").exists()


def test_protect_blocks_dangerous_tool_before_original_is_called(tmp_path: Path) -> None:
    calls: list[str] = []

    @protect(config_path=CONFIG, tool_name="exec_command", user_role="ops", audit_dir=str(tmp_path / "audit"))
    def exec_command(cmd: str) -> str:
        calls.append(cmd)
        return "executed"

    with pytest.raises(XAGuardBlocked) as exc:
        exec_command("rm -rf /")

    assert calls == []
    assert exc.value.decision.value in {"deny", "require_approval"}
    assert exc.value.trace_id
    assert (tmp_path / "audit" / "audit.jsonl").exists()


def test_protect_supports_async_tools(tmp_path: Path) -> None:
    calls: list[str] = []

    @protect(config_path=CONFIG, tool_name="echo", audit_dir=str(tmp_path / "audit_async"))
    async def echo_async(message: str) -> str:
        calls.append(message)
        return f"async:{message}"

    assert asyncio.run(echo_async("hello")) == "async:hello"
    assert calls == ["hello"]
