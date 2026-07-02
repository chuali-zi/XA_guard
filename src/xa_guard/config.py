"""YAML 配置加载。

配置文件结构见 configs/xa-guard.yaml。所有关卡的开关、阈值、文件路径都在此。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml


@dataclass
class GateConfig:
    enabled: bool = True
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class DownstreamSpec:
    name: str
    command: list[str]
    transport: Literal["stdio", "streamable-http"] = "stdio"
    url: str | None = None
    tools: list[dict[str, Any]] = field(default_factory=list)
    env_passthrough: list[str] = field(default_factory=list)


@dataclass
class UpstreamSpec:
    transport: Literal["stdio", "streamable-http"] = "stdio"
    host: str = "127.0.0.1"
    port: int = 3000
    session_idle_timeout_seconds: float = 300.0


@dataclass
class GovernanceConfig:
    enabled: bool = False
    registry_file: str = "configs/governance.demo.yaml"
    default_tenant: str = "default"


def _default_gates() -> dict[str, GateConfig]:
    return {
        "gate5": GateConfig(enabled=False),
    }


@dataclass
class XAGuardConfig:
    upstream: UpstreamSpec = field(default_factory=UpstreamSpec)
    downstream: list[DownstreamSpec] = field(default_factory=list)
    gates: dict[str, GateConfig] = field(default_factory=_default_gates)
    governance: GovernanceConfig = field(default_factory=GovernanceConfig)
    policy_default: str = "enterprise-l3"
    audit_dir: str = "./logs/audit"
    log_dir: str = "./logs/runtime"
    pending_approvals_path: str = ""
    tool_capabilities_file: str = "policies/baseline/gate4_capabilities.yaml"

    @classmethod
    def from_yaml(cls, path: str | Path) -> "XAGuardConfig":
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        root = raw.get("xa_guard", raw)

        upstream_raw = root.get("upstream", {})
        upstream = UpstreamSpec(
            transport=upstream_raw.get("transport", "stdio"),
            host=upstream_raw.get("host", "127.0.0.1"),
            port=int(upstream_raw.get("port", 3000)),
            session_idle_timeout_seconds=float(
                upstream_raw.get("session_idle_timeout_seconds", 300.0)
            ),
        )
        if upstream.session_idle_timeout_seconds <= 0:
            raise ValueError("upstream.session_idle_timeout_seconds must be positive")

        downstream = [
            DownstreamSpec(
                name=item["name"],
                command=list(item.get("command", [])),
                transport=item.get("transport", "stdio"),
                url=item.get("url"),
                tools=list(item.get("tools") or []),
                env_passthrough=list(item.get("env_passthrough") or []),
            )
            for item in root.get("downstream", [])
        ]

        gates = {
            name: GateConfig(
                enabled=spec.get("enabled", True),
                options={k: v for k, v in spec.items() if k != "enabled"},
            )
            for name, spec in (root.get("gates") or {}).items()
        }
        governance_raw = root.get("governance", {}) or {}
        governance = GovernanceConfig(
            enabled=bool(governance_raw.get("enabled", False)),
            registry_file=str(governance_raw.get("registry_file", "configs/governance.demo.yaml")),
            default_tenant=str(governance_raw.get("default_tenant", "default")),
        )

        return cls(
            upstream=upstream,
            downstream=downstream,
            gates=gates,
            governance=governance,
            policy_default=root.get("policy_default", "enterprise-l3"),
            audit_dir=root.get("audit_dir", "./logs/audit"),
            log_dir=root.get("log_dir", "./logs/runtime"),
            pending_approvals_path=root.get("pending_approvals_path", ""),
            tool_capabilities_file=root.get("tool_capabilities_file", "policies/baseline/gate4_capabilities.yaml"),
        )

    def gate(self, name: str) -> GateConfig:
        return self.gates.get(name, GateConfig(enabled=True))
