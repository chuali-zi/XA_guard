from pathlib import Path

import pytest

from xa_guard.integrations.langgraph import protect_node
from xa_guard.sdk import XAGuardBlocked

CONFIG = "configs/xa-guard.docker.yaml"


def test_langgraph_node_is_blocked_before_execution(tmp_path: Path):
    calls = []

    def node(state):
        calls.append(state)
        return {"done": True}

    guarded = protect_node(
        node, tool_name="exec_command", config_path=CONFIG, audit_dir=str(tmp_path / "audit")
    )
    with pytest.raises(XAGuardBlocked):
        guarded({"cmd": "rm -rf /"})
    assert calls == []
