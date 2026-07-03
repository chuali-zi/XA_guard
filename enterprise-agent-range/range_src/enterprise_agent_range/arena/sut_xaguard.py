from __future__ import annotations

import json
import sys
from pathlib import Path

SUT_GUARD = "guard"
SUT_NULL = "null"


def path_text(path: Path) -> str:
    return str(path.resolve())


def yaml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def yaml_list(values: list[str]) -> str:
    return "[" + ", ".join(yaml_string(value) for value in values) + "]"


def find_xa_guard_root(start: Path) -> Path:
    candidates = [start.resolve(), *start.resolve().parents]
    for candidate in candidates:
        if (candidate / "src/xa_guard/server.py").exists():
            return candidate
    sibling_parent = start.resolve().parent
    if (sibling_parent / "src/xa_guard/server.py").exists():
        return sibling_parent
    raise FileNotFoundError("could not locate xa_guard root containing src/xa_guard/server.py")


def office_server_command(
    *,
    world_path: Path,
    principal: str,
    events_out: Path,
    effects_out: Path,
) -> list[str]:
    return [
        sys.executable,
        "-m",
        "enterprise_agent_range.arena.mcp_office_server",
        "--world",
        path_text(world_path),
        "--principal",
        principal,
        "--events-out",
        path_text(events_out),
        "--effects-out",
        path_text(effects_out),
    ]


def write_xa_guard_config(
    *,
    path: Path,
    xa_guard_root: Path,
    office_command: list[str],
    audit_dir: Path,
    pending_path: Path,
    tool_capabilities_file: Path,
    policy_file: Path,
) -> None:
    root = xa_guard_root.resolve()
    text = f"""xa_guard:
  upstream:
    transport: stdio

  downstream:
    - name: office_target
      command: {yaml_list(office_command)}
      transport: stdio
      env_passthrough: [PYTHONPATH, PYTHONIOENCODING]

  gates:
    gate1:
      enabled: true
      detectors:
        - name: rule
          type: rule
          enabled: true
          patterns_file: {yaml_string(path_text(root / "policies/baseline/gate1_input_patterns.yaml"))}
      patterns_file: {yaml_string(path_text(root / "policies/baseline/gate1_input_patterns.yaml"))}
    gate2:
      enabled: true
      hitl_required_for: [red]
      elicitation_fallback: deny
      tool_risk_file: {yaml_string(path_text(root / "policies/baseline/gate2_tool_risks.yaml"))}
      prefer_layered: false
    gate3:
      enabled: true
      backend: python
      policy_file: {yaml_string(path_text(policy_file))}
      prefer_layered: false
    gate4:
      enabled: true
      strict_mode: false
      tool_capabilities_file: {yaml_string(path_text(tool_capabilities_file))}
      prefer_layered: false
    gate5:
      enabled: false
    gate6:
      enabled: true
      audit_dir: {yaml_string(path_text(audit_dir))}
      hash_algo: sha256
    policy_layered:
      enabled: false

  pending_approvals_path: {yaml_string(path_text(pending_path))}
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")