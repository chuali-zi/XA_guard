"""ToolSurface — 仪表化工具面。

契约见 ``docs/architecture/kernel-architecture.md`` §3。移植自 arena ``surface.py``，
补上一个可选的执行 handler，使"工具 = 改/观察世界 + 落账"这条语义在内核里闭环。

铁律：工具只做两件事——(1) 改变或观察世界；(2) 把事实写入账本。
**工具从不判断"这是不是攻击"，也不按攻击路径分支。** allow/deny 由 SUT + Oracle 判。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

# 工具执行 handler 签名：拿到 world/ledger/principal/args，改世界 + 落账，返回给 agent 的输出。
# ledger/world 类型用 Any 以避免内核内部循环 import；实际类型见 world.World / ledger.Ledger。
ToolHandler = Callable[[Any, Any, str, dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class ToolDefinition:
    """一个工具的声明：schema + 能力 + 风险 + taint + 可选执行 handler。"""

    name: str
    description: str
    input_schema: dict[str, Any]
    capabilities: list[str] = field(default_factory=list)
    input_max_taint: str = "PUBLIC"
    output_taint: str = "PUBLIC"
    risk_level: str = "green"
    metadata: dict[str, Any] = field(default_factory=dict)
    handler: ToolHandler | None = None  # None = 仅声明（如 SP2 场景再绑定执行）

    def mcp_schema(self) -> dict[str, Any]:
        """给 agent/SUT 的 MCP 工具 schema。"""
        return {"name": self.name, "description": self.description, "inputSchema": self.input_schema}

    def gate4_yaml(self) -> str:
        """给 SUT（XA-Guard Gate4）的能力声明。"""
        lines = [
            f"  - tool_name: {self.name}",
            f"    capabilities: {_yaml_list(self.capabilities)}",
            f"    input_max_taint: {self.input_max_taint}",
            f"    output_taint: {self.output_taint}",
            f"    risk_level: {self.risk_level}",
        ]
        if self.description:
            lines.append(f"    description: {_yaml_string(self.description)}")
        return "\n".join(lines)


@dataclass(frozen=True)
class ToolSurface:
    """一个世界暴露的工具集合。"""

    name: str
    tools: tuple[ToolDefinition, ...]

    def tool_names(self) -> list[str]:
        return [t.name for t in self.tools]

    def get(self, name: str) -> ToolDefinition:
        for tool in self.tools:
            if tool.name == name:
                return tool
        raise KeyError(f"unknown tool: {name}")

    def mcp_tool_schemas(self) -> list[dict[str, Any]]:
        return [t.mcp_schema() for t in self.tools]

    def gate4_capability_yaml(self) -> str:
        return "\n\n".join(t.gate4_yaml() for t in self.tools) + "\n"

    def gate4_capability_document(self) -> str:
        return f"tools:\n{self.gate4_capability_yaml()}"

    def execute(self, name: str, world: Any, ledger: Any, principal: str, args: dict[str, Any]) -> dict[str, Any]:
        """执行一个工具：委托给 ToolDefinition.handler。SUT 放行后调用它。"""
        tool = self.get(name)
        if tool.handler is None:
            raise NotImplementedError(
                f"TODO: tool '{name}' 未绑定 handler（场景需提供执行体）"
            )
        return tool.handler(world, ledger, principal, dict(args))


def _yaml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _yaml_list(values: list[str]) -> str:
    return "[" + ", ".join(_yaml_string(v) for v in values) + "]"
