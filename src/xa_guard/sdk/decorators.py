"""Small SDK wrapper for protecting Python/LangChain-style tools.

The decorator is intentionally thin: it runs an XA-Guard preflight before the
wrapped function is called. If the pipeline blocks or requires approval, the
original function is not invoked.
"""
from __future__ import annotations

import asyncio
import inspect
from functools import lru_cache, wraps
from pathlib import Path
from typing import Any, Callable

from xa_guard.config import XAGuardConfig
from xa_guard.server import build_pipeline
from xa_guard.types import Decision, GateContext, InputSource


class XAGuardBlocked(RuntimeError):
    """Raised when XA-Guard blocks a protected SDK call."""

    def __init__(self, *, decision: Decision, reason: str, trace_id: str, rule_hits: list[str]) -> None:
        self.decision = decision
        self.reason = reason
        self.trace_id = trace_id
        self.rule_hits = rule_hits
        super().__init__(f"XA-Guard blocked call: decision={decision.value} trace_id={trace_id} reason={reason}")


@lru_cache(maxsize=16)
def _pipeline(config_path: str, audit_dir: str | None):
    cfg = XAGuardConfig.from_yaml(config_path)
    if audit_dir:
        gate6 = cfg.gates.get("gate6")
        if gate6 is not None:
            gate6.options["audit_dir"] = audit_dir
        cfg.audit_dir = audit_dir
    return build_pipeline(cfg)


def _arguments(fn: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    try:
        bound = inspect.signature(fn).bind_partial(*args, **kwargs)
        return dict(bound.arguments)
    except Exception:
        return {"args": list(args), "kwargs": dict(kwargs)}


def _sources(values: list[str | InputSource] | tuple[str | InputSource, ...] | None) -> list[InputSource]:
    if not values:
        return [InputSource.USER]
    return [value if isinstance(value, InputSource) else InputSource(str(value)) for value in values]


async def _preflight(
    *,
    fn: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    config_path: str,
    audit_dir: str | None,
    tool_name: str | None,
    user_role: str,
    input_sources: list[str | InputSource] | tuple[str | InputSource, ...] | None,
) -> GateContext:
    return await preflight_tool_call(
        tool_name=tool_name or fn.__name__,
        arguments=_arguments(fn, args, kwargs),
        config_path=config_path,
        audit_dir=audit_dir,
        user_role=user_role,
        input_sources=input_sources,
    )


async def preflight_tool_call(
    *,
    tool_name: str,
    arguments: dict[str, Any],
    config_path: str = "configs/xa-guard.yaml",
    audit_dir: str | None = None,
    user_role: str = "user",
    input_sources: list[str | InputSource] | tuple[str | InputSource, ...] | None = None,
) -> GateContext:
    """Run XA-Guard preflight for SDK integrations without executing the tool."""
    pipeline = _pipeline(str(Path(config_path)), audit_dir)
    ctx = GateContext(
        tool_name=tool_name,
        arguments=arguments,
        user_role=user_role,
        input_sources=_sources(input_sources),
    )

    async def _executor(c: GateContext) -> dict[str, Any]:
        return {"sdk_preflight": True, "tool": c.tool_name}

    result = await pipeline.run(ctx, _executor)
    if (not result.allowed) or result.final_decision == Decision.REQUIRE_APPROVAL:
        raise XAGuardBlocked(
            decision=result.final_decision,
            reason=result.final_reason,
            trace_id=ctx.trace_id,
            rule_hits=list(ctx.rule_hits),
        )
    return ctx


def protect(
    policy: str = "enterprise-l3",
    *,
    config_path: str = "configs/xa-guard.yaml",
    tool_name: str | None = None,
    user_role: str = "user",
    input_sources: list[str | InputSource] | tuple[str | InputSource, ...] | None = None,
    audit_dir: str | None = None,
):
    """Protect a sync or async Python tool with XA-Guard.

    ``policy`` is kept for the public SDK API and maps to the policy selected in
    the config file. The current implementation enforces by running the normal
    XA-Guard pipeline as a preflight.
    """

    def deco(fn):
        if inspect.iscoroutinefunction(fn):

            @wraps(fn)
            async def async_wrapper(*args, **kwargs):
                await _preflight(
                    fn=fn,
                    args=args,
                    kwargs=kwargs,
                    config_path=config_path,
                    audit_dir=audit_dir,
                    tool_name=tool_name,
                    user_role=user_role,
                    input_sources=input_sources,
                )
                return await fn(*args, **kwargs)

            async_wrapper.xa_guard_policy = policy
            return async_wrapper

        @wraps(fn)
        def sync_wrapper(*args, **kwargs):
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                asyncio.run(
                    _preflight(
                        fn=fn,
                        args=args,
                        kwargs=kwargs,
                        config_path=config_path,
                        audit_dir=audit_dir,
                        tool_name=tool_name,
                        user_role=user_role,
                        input_sources=input_sources,
                    )
                )
            else:
                raise RuntimeError("XA-Guard sync @protect cannot run inside an active event loop; use an async tool")
            return fn(*args, **kwargs)

        sync_wrapper.xa_guard_policy = policy
        return sync_wrapper

    return deco
