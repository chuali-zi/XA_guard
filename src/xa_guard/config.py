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


@dataclass
class IdentityIssuerConfig:
    issuer: str
    audiences: list[str] = field(default_factory=list)
    jwks_file: str = ""
    jwks_uri: str = ""
    algorithms: list[str] = field(default_factory=lambda: ["RS256", "ES256", "EdDSA"])


@dataclass
class IdentityConfig:
    enabled: bool = False
    required: bool = False
    required_scopes: list[str] = field(default_factory=lambda: ["xa.invoke"])
    issuers: list[IdentityIssuerConfig] = field(default_factory=list)
    stdio_token_env: str = "XA_GUARD_IDENTITY_TOKEN"
    max_token_ttl_seconds: int = 300
    clock_skew_seconds: int = 30


@dataclass
class ResilienceConfig:
    enabled: bool = False
    contracts_file: str = "policies/baseline/tool_effects.yaml"
    store_path: str = "./logs/resilience/effects.sqlite3"
    key_env: str = "XA_GUARD_RECOVERY_KEY"
    key_id: str = ""


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
    identity: IdentityConfig = field(default_factory=IdentityConfig)
    resilience: ResilienceConfig = field(default_factory=ResilienceConfig)
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
        identity_raw = root.get("identity", {}) or {}
        identity = IdentityConfig(
            enabled=bool(identity_raw.get("enabled", False)),
            required=bool(identity_raw.get("required", False)),
            required_scopes=[str(v) for v in identity_raw.get("required_scopes", ["xa.invoke"])],
            issuers=[
                IdentityIssuerConfig(
                    issuer=str(item["issuer"]),
                    audiences=[str(v) for v in item.get("audiences", [])],
                    jwks_file=str(item.get("jwks_file", "")),
                    jwks_uri=str(item.get("jwks_uri", "")),
                    algorithms=[str(v) for v in item.get("algorithms", ["RS256", "ES256", "EdDSA"])],
                )
                for item in identity_raw.get("issuers", [])
            ],
            stdio_token_env=str(identity_raw.get("stdio_token_env", "XA_GUARD_IDENTITY_TOKEN")),
            max_token_ttl_seconds=int(identity_raw.get("max_token_ttl_seconds", 300)),
            clock_skew_seconds=int(identity_raw.get("clock_skew_seconds", 30)),
        )
        resilience_raw = root.get("resilience", {}) or {}
        resilience = ResilienceConfig(
            enabled=bool(resilience_raw.get("enabled", False)),
            contracts_file=str(resilience_raw.get("contracts_file", "policies/baseline/tool_effects.yaml")),
            store_path=str(resilience_raw.get("store_path", "./logs/resilience/effects.sqlite3")),
            key_env=str(resilience_raw.get("key_env", "XA_GUARD_RECOVERY_KEY")),
            key_id=str(resilience_raw.get("key_id", "")),
        )
        if identity.required and not identity.enabled:
            raise ValueError("identity.required requires identity.enabled=true")
        if identity.enabled and not identity.issuers:
            raise ValueError("identity.enabled requires at least one allowlisted issuer")

        return cls(
            upstream=upstream,
            downstream=downstream,
            gates=gates,
            governance=governance,
            identity=identity,
            resilience=resilience,
            policy_default=root.get("policy_default", "enterprise-l3"),
            audit_dir=root.get("audit_dir", "./logs/audit"),
            log_dir=root.get("log_dir", "./logs/runtime"),
            pending_approvals_path=root.get("pending_approvals_path", ""),
            tool_capabilities_file=root.get("tool_capabilities_file", "policies/baseline/gate4_capabilities.yaml"),
        )

    def gate(self, name: str) -> GateConfig:
        return self.gates.get(name, GateConfig(enabled=True))
