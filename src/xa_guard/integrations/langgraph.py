"""Static-safe LangGraph node and tool adapters."""

from __future__ import annotations
from typing import Any, Callable
from xa_guard.integrations.langchain import guard_callable, protect_tool, protect_tools


def protect_node(node: Callable[..., Any], **kwargs: Any) -> Callable[..., Any]:
    """Wrap a graph node so preflight runs before node execution."""
    return guard_callable(node, **kwargs)


guard_node = protect_node
__all__ = ["guard_node", "protect_node", "protect_tool", "protect_tools"]
