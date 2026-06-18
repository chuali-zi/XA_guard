from __future__ import annotations

import asyncio
from pathlib import Path

from xa_guard.config import XAGuardConfig
from xa_guard.proxy.downstream import DownstreamRouter


def test_l3_compose_static_downstream_manifest_exposes_tools_without_native_sessions():
    cfg = XAGuardConfig.from_yaml(Path("configs") / "xa-guard.docker.yaml")
    router = DownstreamRouter(cfg.downstream)

    asyncio.run(router.start())
    try:
        tools = router.list_tools()
        names = {tool["name"] for tool in tools}

        assert {"list_servers", "get_cpu", "exec_command", "send_email"} <= names
        assert router._sessions == {}
        assert all(session is None for _, session in router.tools_by_name.values())
    finally:
        asyncio.run(router.stop())
