"""LangChain tool integration.

This module intentionally provides a strong Tool wrapper first. Callback-based
blocking is more fragile because callback exceptions may be swallowed by some
execution paths.
"""
from __future__ import annotations

import asyncio
import copy
from typing import Any

from xa_guard.sdk.decorators import XAGuardBlocked, preflight_tool_call
from xa_guard.types import InputSource


def _call_arguments(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    if len(args) == 1 and isinstance(args[0], dict) and not kwargs:
        return dict(args[0])
    if len(args) == 1 and not kwargs:
        return {"input": args[0]}
    return {"args": list(args), "kwargs": dict(kwargs)}


def _run_sync_preflight(**kwargs: Any) -> None:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(preflight_tool_call(**kwargs))
    else:
        raise RuntimeError("XA-Guard LangChain sync tool wrapper cannot run inside an active event loop")


def protect_tool(
    tool: Any,
    *,
    config_path: str = "configs/xa-guard.yaml",
    tool_name: str | None = None,
    user_role: str = "user",
    input_sources: list[str | InputSource] | tuple[str | InputSource, ...] | None = None,
    audit_dir: str | None = None,
) -> Any:
    """Wrap a LangChain BaseTool so XA-Guard preflight runs before execution.

    The returned object is a shallow copy of the original tool with guarded
    ``_run`` / ``_arun`` methods. DENY and REQUIRE_APPROVAL raise
    :class:`XAGuardBlocked`, and the original tool method is not called.
    """
    try:
        from langchain_core.tools import BaseTool
    except Exception as exc:  # pragma: no cover - exercised only without sdk extra
        raise ImportError("protect_tool requires the 'xa-guard[sdk]' extra with langchain-core") from exc

    if not isinstance(tool, BaseTool):
        raise TypeError("protect_tool expects a langchain_core.tools.BaseTool instance")

    protected = copy.copy(tool)
    resolved_name = tool_name or getattr(tool, "name", None) or tool.__class__.__name__
    original_run = getattr(tool, "_run")
    original_arun = getattr(tool, "_arun", None)

    def guarded_run(*args: Any, **kwargs: Any) -> Any:
        _run_sync_preflight(
            tool_name=resolved_name,
            arguments=_call_arguments(args, kwargs),
            config_path=config_path,
            audit_dir=audit_dir,
            user_role=user_role,
            input_sources=input_sources,
        )
        return original_run(*args, **kwargs)

    async def guarded_arun(*args: Any, **kwargs: Any) -> Any:
        await preflight_tool_call(
            tool_name=resolved_name,
            arguments=_call_arguments(args, kwargs),
            config_path=config_path,
            audit_dir=audit_dir,
            user_role=user_role,
            input_sources=input_sources,
        )
        if original_arun is None:
            return original_run(*args, **kwargs)
        return await original_arun(*args, **kwargs)

    object.__setattr__(protected, "_run", guarded_run)
    object.__setattr__(protected, "_arun", guarded_arun)
    object.__setattr__(protected, "xa_guard_protected", True)
    object.__setattr__(protected, "xa_guard_tool_name", resolved_name)
    return protected
