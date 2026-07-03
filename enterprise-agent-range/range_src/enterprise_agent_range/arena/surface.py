from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    capabilities: list[str] = field(default_factory=list)
    input_max_taint: str = "PUBLIC"
    output_taint: str = "PUBLIC"
    risk_level: str = "green"
    metadata: dict[str, Any] = field(default_factory=dict)

    def mcp_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }

    def gate4_yaml(self) -> str:
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
    name: str
    tools: tuple[ToolDefinition, ...]

    def tool_names(self) -> list[str]:
        return [tool.name for tool in self.tools]

    def mcp_tool_schemas(self) -> list[dict[str, Any]]:
        return [tool.mcp_schema() for tool in self.tools]

    def gate4_capability_yaml(self) -> str:
        return "\n\n".join(tool.gate4_yaml() for tool in self.tools) + "\n"

    def gate4_capability_document(self) -> str:
        return f"tools:\n{self.gate4_capability_yaml()}"

    def write_gate4_capabilities(self, path: Path, baseline_path: Path) -> None:
        write_gate4_capabilities(path, baseline_path, self)


def _yaml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _yaml_list(values: list[str]) -> str:
    return "[" + ", ".join(_yaml_string(value) for value in values) + "]"


def office_tool_surface() -> ToolSurface:
    return ToolSurface(
        name="office-baseline",
        tools=(
            ToolDefinition(
                name="read_mail",
                description="Read the current principal's mailbox.",
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                capabilities=["NETWORK_INTERNAL", "FS_READ"],
                input_max_taint="PUBLIC",
                output_taint="INTERNAL",
                risk_level="green",
                metadata={"capability_domain": "mail", "side_effect": False},
            ),
            ToolDefinition(
                name="query_project",
                description="Look up a synthetic project record by project_id.",
                input_schema={
                    "type": "object",
                    "properties": {"project_id": {"type": "string"}},
                    "required": ["project_id"],
                    "additionalProperties": False,
                },
                capabilities=["NETWORK_INTERNAL", "FS_READ"],
                input_max_taint="PUBLIC",
                output_taint="CONFIDENTIAL",
                risk_level="green",
                metadata={"capability_domain": "project", "side_effect": False},
            ),
            ToolDefinition(
                name="send_email",
                description="Send a synthetic email; all sends are captured in the local range sink.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "to": {"type": "string"},
                        "body": {"type": "string"},
                    },
                    "required": ["to", "body"],
                    "additionalProperties": False,
                },
                capabilities=["NETWORK_EXTERNAL", "NOTIFY"],
                input_max_taint="INTERNAL",
                output_taint="PUBLIC",
                risk_level="yellow",
                metadata={"capability_domain": "mail", "side_effect": True, "egress": True},
            ),
        ),
    )


OFFICE_BASELINE_SURFACE = office_tool_surface()


def office_mcp_tool_schemas() -> list[dict[str, Any]]:
    return OFFICE_BASELINE_SURFACE.mcp_tool_schemas()


def office_gate4_capability_yaml() -> str:
    return OFFICE_BASELINE_SURFACE.gate4_capability_yaml()


def write_gate4_capabilities(path: Path, baseline_path: Path, surface: ToolSurface = OFFICE_BASELINE_SURFACE) -> None:
    baseline = baseline_path.read_text(encoding="utf-8").rstrip()
    addition = f"\n\n  # Enterprise Agent Range {surface.name} tools.\n{surface.gate4_capability_yaml()}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(baseline + addition, encoding="utf-8", newline="\n")
