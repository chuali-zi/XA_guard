"""下游 MCP Client：连接真实工具（filesystem / shell / demo targets / ...）。

实现：mcp>=1.27 client API（stdio_client + ClientSession + AsyncExitStack）。
- 每个 DownstreamSpec.command 启动为子进程（stdio transport）。
- start() 初始化 ClientSession，调 list_tools 缓存。
- list_tools() 聚合所有下游工具（dict 形式）。
- call_tool(ctx) 路由到对应 session。
- stop() 优雅关闭所有 session（依靠 AsyncExitStack）。

仅支持 transport="stdio"。streamable-http 下游留 TODO。
"""
from __future__ import annotations

import logging
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from xa_guard.config import DownstreamSpec
from xa_guard.sandbox import SandboxPolicy, build_docker_command, policy_from_context
from xa_guard.types import GateContext

log = logging.getLogger("xa_guard.proxy.downstream")


class DownstreamRouter:
    def __init__(self, specs: list[DownstreamSpec]) -> None:
        self.specs = specs
        # tool_name -> (spec, ClientSession)
        self.tools_by_name: dict[str, tuple[DownstreamSpec, ClientSession]] = {}
        # spec.name -> list of raw tool dicts（保留 list_tools 顺序）
        self._tools_meta: list[dict[str, Any]] = []
        self._stack: AsyncExitStack | None = None
        self._sessions: dict[str, ClientSession] = {}

    async def start(self) -> None:
        if self._stack is not None:
            return
        stack = AsyncExitStack()
        try:
            for spec in self.specs:
                if spec.transport != "stdio":
                    # TODO(agent-P): 支持 streamable-http 下游
                    log.warning("downstream %s transport=%s not yet supported, skip", spec.name, spec.transport)
                    continue
                if not spec.command:
                    log.warning("downstream %s has empty command, skip", spec.name)
                    continue

                params = StdioServerParameters(
                    command=spec.command[0],
                    args=list(spec.command[1:]),
                )
                read_stream, write_stream = await stack.enter_async_context(stdio_client(params))
                session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
                await session.initialize()
                self._sessions[spec.name] = session

                listed = await session.list_tools()
                for tool in listed.tools:
                    if tool.name in self.tools_by_name:
                        log.warning(
                            "tool name conflict: %s already registered by %s, overwriting from %s",
                            tool.name,
                            self.tools_by_name[tool.name][0].name,
                            spec.name,
                        )
                    self.tools_by_name[tool.name] = (spec, session)
                    self._tools_meta.append(
                        {
                            "name": tool.name,
                            "description": tool.description or "",
                            "inputSchema": tool.inputSchema or {"type": "object", "properties": {}},
                            "_downstream": spec.name,
                        }
                    )
                log.info("downstream %s started, %d tools", spec.name, len(listed.tools))
        except Exception:
            await stack.aclose()
            raise

        self._stack = stack

    async def stop(self) -> None:
        if self._stack is None:
            return
        try:
            await self._stack.aclose()
        except Exception:
            log.exception("downstream stop encountered error")
        finally:
            self._stack = None
            self._sessions.clear()
            self.tools_by_name.clear()
            self._tools_meta.clear()

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {"name": t["name"], "description": t["description"], "inputSchema": t["inputSchema"]}
            for t in self._tools_meta
        ]

    async def call_tool(self, ctx: GateContext) -> Any:
        if ctx.tool_name not in self.tools_by_name:
            raise KeyError(f"unknown tool: {ctx.tool_name}")
        spec, session = self.tools_by_name[ctx.tool_name]
        policy = policy_from_context(ctx)
        if policy.enforced:
            return await self._call_tool_sandboxed(spec, ctx, policy)
        log.debug("routing %s -> downstream %s", ctx.tool_name, spec.name)
        result = await session.call_tool(ctx.tool_name, ctx.arguments or {})
        return result

    async def _call_tool_sandboxed(self, spec: DownstreamSpec, ctx: GateContext, policy: SandboxPolicy) -> Any:
        """Run one downstream MCP call through an ephemeral Docker/gVisor server."""
        if spec.transport != "stdio":
            raise NotImplementedError("sandboxed downstream calls currently require stdio transport")

        command = build_docker_command(spec.command, policy, workspace_root=Path.cwd())
        params = StdioServerParameters(command=command[0], args=command[1:])
        log.debug("sandbox routing %s -> downstream %s via %s", ctx.tool_name, spec.name, policy.mode)

        async with AsyncExitStack() as stack:
            read_stream, write_stream = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
            await session.initialize()
            return await session.call_tool(ctx.tool_name, ctx.arguments or {})
