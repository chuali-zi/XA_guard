"""Static-safe LangChain adapters with enforced preflight and HITL resume."""

from __future__ import annotations

import asyncio
import copy
import inspect
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from xa_guard.approval import issue_approval
from xa_guard.sdk.decorators import XAGuardBlocked, _pipeline, _sources
from xa_guard.types import Decision, GateContext, InputSource

try:
    from langchain_core.callbacks import BaseCallbackHandler as _BaseCallbackHandler
except ImportError:  # LangChain is an optional dependency.
    _BaseCallbackHandler = object

_INTERNAL = {"run_manager", "callbacks", "config"}


def _call_arguments(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    kwargs = {k: v for k, v in kwargs.items() if k not in _INTERNAL}
    if len(args) == 1 and isinstance(args[0], dict) and not kwargs:
        return dict(args[0])
    if len(args) == 1 and not kwargs:
        return {"input": args[0]}
    return {"args": list(args), "kwargs": kwargs}


def _blocked(ctx: GateContext) -> XAGuardBlocked:
    return XAGuardBlocked(
        decision=ctx.final_decision,
        reason=ctx.final_reason,
        trace_id=ctx.trace_id,
        rule_hits=list(ctx.rule_hits),
    )


def _run_sync(awaitable: Awaitable[Any]) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    if inspect.iscoroutine(awaitable):
        awaitable.close()
    raise RuntimeError("XA-Guard sync wrapper cannot run inside an active event loop")


@dataclass
class ApprovalRequest:
    """A suspended call which can be approved or denied exactly once."""

    ctx: GateContext
    pipeline: Any
    executor: Callable[[GateContext], Awaitable[Any]]
    _resolved: bool = field(default=False, init=False)

    async def approve(self, *, approver: str, reason: str = "", ttl_seconds: int = 300) -> Any:
        if self._resolved:
            raise RuntimeError("XA-Guard approval request has already been resolved")
        self._resolved = True
        self.ctx.approval = issue_approval(
            trace_id=self.ctx.trace_id,
            tool_name=self.ctx.tool_name,
            arguments=self.ctx.arguments,
            approver=approver,
            reason=reason,
            ttl_seconds=ttl_seconds,
        )
        result = await self.pipeline.run_after_approval(self.ctx, self.executor)
        if not result.allowed:
            raise _blocked(self.ctx)
        return result.tool_result

    async def deny(self, *, approver: str, reason: str = "") -> None:
        if self._resolved:
            raise RuntimeError("XA-Guard approval request has already been resolved")
        self._resolved = True
        await self.pipeline.reject_after_approval(self.ctx, approver=approver, reason=reason)

    def approve_sync(self, **kwargs: Any) -> Any:
        return _run_sync(self.approve(**kwargs))

    def deny_sync(self, **kwargs: Any) -> None:
        _run_sync(self.deny(**kwargs))


class XAGuardApprovalRequired(XAGuardBlocked):
    """Blocked call carrying a request that can resume the exact invocation."""

    def __init__(self, request: ApprovalRequest) -> None:
        self.request = request
        ctx = request.ctx
        super().__init__(
            decision=ctx.final_decision,
            reason=ctx.final_reason,
            trace_id=ctx.trace_id,
            rule_hits=list(ctx.rule_hits),
        )


async def _guarded_call(
    executor: Callable[[GateContext], Awaitable[Any]],
    *,
    tool_name: str,
    arguments: dict[str, Any],
    config_path: str,
    audit_dir: str | None,
    user_role: str,
    input_sources: list[str | InputSource] | tuple[str | InputSource, ...] | None,
) -> Any:
    pipeline = _pipeline(config_path, audit_dir)
    ctx = GateContext(
        tool_name=tool_name, arguments=arguments, user_role=user_role, input_sources=_sources(input_sources)
    )
    result = await pipeline.run(ctx, executor)
    if result.final_decision == Decision.REQUIRE_APPROVAL:
        raise XAGuardApprovalRequired(ApprovalRequest(ctx, pipeline, executor))
    if not result.allowed:
        raise _blocked(ctx)
    return result.tool_result


def guard_callable(
    fn: Callable[..., Any],
    *,
    tool_name: str | None = None,
    config_path: str = "configs/xa-guard.yaml",
    user_role: str = "user",
    input_sources: list[str | InputSource] | tuple[str | InputSource, ...] | None = None,
    audit_dir: str | None = None,
) -> Callable[..., Any]:
    """Guard a sync or async Agent/LangGraph node before invocation."""
    name = tool_name or getattr(fn, "name", None) or getattr(fn, "__name__", type(fn).__name__)
    options = dict(
        tool_name=name,
        config_path=config_path,
        audit_dir=audit_dir,
        user_role=user_role,
        input_sources=input_sources,
    )
    if inspect.iscoroutinefunction(fn):

        async def async_guarded(*args: Any, **kwargs: Any) -> Any:
            async def execute(_: GateContext) -> Any:
                return await fn(*args, **kwargs)

            return await _guarded_call(execute, arguments=_call_arguments(args, kwargs), **options)

        async_guarded.__name__ = getattr(fn, "__name__", "xa_guard_async_node")
        return async_guarded

    def sync_guarded(*args: Any, **kwargs: Any) -> Any:
        async def execute(_: GateContext) -> Any:
            return fn(*args, **kwargs)

        return _run_sync(_guarded_call(execute, arguments=_call_arguments(args, kwargs), **options))

    sync_guarded.__name__ = getattr(fn, "__name__", "xa_guard_node")
    return sync_guarded


def protect_tool(
    tool: Any,
    *,
    config_path: str = "configs/xa-guard.yaml",
    tool_name: str | None = None,
    user_role: str = "user",
    input_sources: list[str | InputSource] | tuple[str | InputSource, ...] | None = None,
    audit_dir: str | None = None,
) -> Any:
    """Return a BaseTool copy guarded before sync and async execution."""
    try:
        from langchain_core.tools import BaseTool
    except ImportError as exc:
        raise ImportError("protect_tool requires the 'xa-guard[sdk]' extra with langchain-core") from exc
    if not isinstance(tool, BaseTool):
        raise TypeError("protect_tool expects a langchain_core.tools.BaseTool instance")
    protected = copy.copy(tool)
    name = tool_name or getattr(tool, "name", None) or tool.__class__.__name__
    common = dict(
        tool_name=name,
        config_path=config_path,
        user_role=user_role,
        input_sources=input_sources,
        audit_dir=audit_dir,
    )
    object.__setattr__(protected, "_run", guard_callable(tool._run, **common))
    original_arun = getattr(tool, "_arun", None)

    async def guarded_arun(*args: Any, **kwargs: Any) -> Any:
        async def execute(_: GateContext) -> Any:
            if original_arun is None:
                return tool._run(*args, **kwargs)
            return await original_arun(*args, **kwargs)

        return await _guarded_call(execute, arguments=_call_arguments(args, kwargs), **common)

    object.__setattr__(protected, "_arun", guarded_arun)
    object.__setattr__(protected, "xa_guard_protected", True)
    object.__setattr__(protected, "xa_guard_tool_name", name)
    return protected


def protect_tools(tools: list[Any] | tuple[Any, ...], **kwargs: Any) -> list[Any]:
    return [protect_tool(tool, **kwargs) for tool in tools]


def protect_runnable(runnable: Any, **kwargs: Any) -> Any:
    """Guard Agent/Runnable invoke and ainvoke entrypoints."""
    protected = copy.copy(runnable)
    found = False
    for method in ("invoke", "ainvoke"):
        fn = getattr(runnable, method, None)
        if callable(fn):
            object.__setattr__(protected, method, guard_callable(fn, **kwargs))
            found = True
    if not found:
        raise TypeError("protect_runnable expects an object with invoke or ainvoke")
    object.__setattr__(protected, "xa_guard_protected", True)
    return protected


protect_agent = protect_runnable


class XAGuardCallbackHandler(_BaseCallbackHandler):
    """Dependency-free callback observer; wrappers remain the enforcement point."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def on_tool_start(self, serialized: dict[str, Any], input_str: str, **kwargs: Any) -> None:
        self.events.append({"event": "tool_start", "name": serialized.get("name", ""), "input": input_str})

    def on_tool_end(self, output: Any, **kwargs: Any) -> None:
        self.events.append({"event": "tool_end", "output": output})

    def on_tool_error(self, error: BaseException, **kwargs: Any) -> None:
        self.events.append({"event": "tool_error", "error": type(error).__name__})


__all__ = [
    "ApprovalRequest",
    "XAGuardApprovalRequired",
    "XAGuardCallbackHandler",
    "guard_callable",
    "protect_agent",
    "protect_runnable",
    "protect_tool",
    "protect_tools",
]
