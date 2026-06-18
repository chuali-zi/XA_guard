"""Export the effective layered policy view as OPA-ready artifacts."""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from xa_guard.policy.layered import LayeredPolicySource
from xa_guard.policy.rego import build_rego_module
from xa_guard.types import Decision, PolicyRule, RiskLevel, TaintLabel, ToolCapability


def _json_default(value: Any) -> Any:
    if isinstance(value, (Decision, RiskLevel, TaintLabel)):
        return value.value
    raise TypeError(f"cannot serialize {type(value).__name__}")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _rule_to_dict(rule: PolicyRule) -> dict[str, Any]:
    data = asdict(rule)
    data["enforce"] = rule.enforce.value
    return data


def _cap_to_dict(cap: ToolCapability) -> dict[str, Any]:
    data = asdict(cap)
    data["input_max_taint"] = cap.input_max_taint.value
    data["output_taint"] = cap.output_taint.value
    data["risk_level"] = cap.risk_level.value
    return data


def build_opa_data(source: LayeredPolicySource) -> dict[str, Any]:
    """Return the effective baseline+accepted-overlay policy view as OPA data."""
    return {
        "xa_guard": {
            "policy": {
                "schema_version": "xa-guard-opa-policy-data/v0.1",
                "bundle_sha": source.bundle_sha,
                "stats": source.stats(),
                "overlay_rejections": source.overlay_rejections,
                "rules": [_rule_to_dict(rule) for rule in source.get_policy_rules()],
                "tool_risks": {
                    name: risk.value
                    for name, risk in sorted(source.get_tool_risks().items())
                },
                "tool_capabilities": {
                    name: _cap_to_dict(cap)
                    for name, cap in sorted(source.get_tool_capabilities().items())
                },
                "sensitive_patterns": source.get_sensitive_patterns(),
            }
        }
    }


def write_opa_bundle(
    source: LayeredPolicySource,
    out_dir: str | Path,
    *,
    package: str = "xa_guard.gate3",
) -> dict[str, Any]:
    """Write data.json, gate3.rego, and manifest.json for OPA deployment review."""
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)

    data = build_opa_data(source)
    rego_module = build_rego_module(source.get_policy_rules(), package=package)
    generated_at = _utc_now()
    paths = {
        "data": target / "data.json",
        "rego": target / "gate3.rego",
        "manifest": target / "manifest.json",
    }

    paths["data"].write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )
    paths["rego"].write_text(rego_module, encoding="utf-8")

    manifest = {
        "schema_version": "xa-guard-opa-bundle-manifest/v0.1",
        "generated_at": generated_at,
        "package": package,
        "bundle_sha": source.bundle_sha,
        "stats": source.stats(),
        "overlay_rejections": source.overlay_rejections,
        "artifacts": {name: str(path) for name, path in paths.items()},
        "note": "OPA export of current LayeredPolicySource baseline plus accepted overlays; not a proof that OPA CLI was executed",
    }
    paths["manifest"].write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest
