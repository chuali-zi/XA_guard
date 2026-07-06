"""PolicyOverlay — 场景策略覆盖，生成 Gate3/Gate4 证据配置。

移植自 arena ``policy_overlay.py``，适配内核 Scenario（非 Challenge）。
场景通过 ``policy`` 字段声明 ``sensitive_markers`` / ``deny_external_tools``；
内核不写死具体机密或攻击标记（decoupling-contract §1）。

生成物属于证据包（gate3-rules.yaml / gate4-capabilities.yaml），不是 XA-Guard 源码。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_DENY_EXTERNAL_TOOLS = ("send_email", "send", "send_message")


@dataclass(frozen=True)
class PolicyOverlay:
    scenario_id: str
    sensitive_markers: tuple[str, ...] = field(default_factory=tuple)
    deny_external_tools: tuple[str, ...] = field(default_factory=tuple)

    def gate3_rule_yaml(self) -> str:
        tools = self.deny_external_tools or DEFAULT_DENY_EXTERNAL_TOOLS
        markers = self.sensitive_markers
        if not markers:
            return ""
        rule_id = f"OAR-{_yaml_id(self.scenario_id)}-EGRESS"
        predicate = _predicate_for_markers(tools, markers)
        return "\n".join(
            [
                f"  - id: {rule_id}",
                f"    name: {_yaml_string('Open Agent Range sensitive external egress deny')}",
                f"    source: {_yaml_string('Open Agent Range scenario policy')}",
                f"    triggers: {_yaml_list(list(tools))}",
                f"    predicate: {_yaml_string(predicate)}",
                "    enforce: deny",
                "    severity: critical",
                "    audit: required",
                f"    description: {_yaml_string('Scenario-specific sensitive markers must not egress via external tools.')}",
                "",
            ]
        )

    def write_gate3_policy(self, path: Path, baseline_path: Path) -> None:
        write_gate3_policy(path, baseline_path, self)


def overlay_from_scenario_data(data: dict[str, Any]) -> PolicyOverlay:
    policy = data.get("policy", {})
    if not isinstance(policy, dict):
        policy = {}
    return PolicyOverlay(
        scenario_id=str(data.get("scenario_id", "scenario")),
        sensitive_markers=tuple(_clean_strings(policy.get("sensitive_markers", []))),
        deny_external_tools=tuple(_clean_strings(policy.get("deny_external_tools", []))),
    )


def overlay_from_scenario(scenario: Any) -> PolicyOverlay:
    """从 Scenario 实例或带 policy 字段的对象构建 overlay。"""
    policy = getattr(scenario, "policy", None)
    if isinstance(policy, dict):
        return PolicyOverlay(
            scenario_id=str(getattr(scenario, "scenario_id", "scenario")),
            sensitive_markers=tuple(_clean_strings(policy.get("sensitive_markers", []))),
            deny_external_tools=tuple(_clean_strings(policy.get("deny_external_tools", []))),
        )
    return PolicyOverlay(scenario_id=str(getattr(scenario, "scenario_id", "scenario")))


def write_gate3_policy(path: Path, baseline_path: Path, overlay: PolicyOverlay) -> None:
    baseline = baseline_path.read_text(encoding="utf-8").rstrip()
    rule = overlay.gate3_rule_yaml()
    path.parent.mkdir(parents=True, exist_ok=True)
    if rule:
        path.write_text(baseline + "\n\n" + rule, encoding="utf-8", newline="\n")
    else:
        path.write_text(baseline + "\n", encoding="utf-8", newline="\n")


def _clean_strings(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(value) for value in values if str(value)]


def _yaml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _yaml_list(values: list[str]) -> str:
    return "[" + ", ".join(_yaml_string(value) for value in values) + "]"


def _yaml_id(value: str) -> str:
    return "".join(ch.upper() if ch.isalnum() else "-" for ch in value).strip("-") or "SCENARIO"


def _predicate_literal(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _predicate_for_markers(tools: tuple[str, ...], markers: tuple[str, ...]) -> str:
    tool_predicate = f"tool == {_predicate_literal(tools[0])}"
    if len(tools) > 1:
        tool_predicate = "tool in (" + ", ".join(_predicate_literal(tool) for tool in tools) + ")"
    fields = ("body", "content", "text")
    marker_predicate = " or ".join(
        f"contains({_predicate_literal(field)}, {_predicate_literal(marker)})"
        for marker in markers
        for field in fields
    )
    return f"{tool_predicate} and ({marker_predicate})"
