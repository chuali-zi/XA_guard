"""Versioned side-effect contracts and strict write-tool admission."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from xa_guard.control.crypto import sha256_json
from xa_guard.control.models import EffectContractV2


class ContractError(RuntimeError):
    pass


class ContractRegistry:
    WRITE_CAPABILITIES = {
        "FS_WRITE", "EXEC", "NOTIFY", "CONTENT_PUBLISH", "PAYMENT", "POLICY_ADMIN",
        "AUTHZ_ADMIN", "AUDIT_ADMIN", "MODEL_TRAINING", "MODEL_DEPLOY", "DATA_INGEST",
    }

    def __init__(self, contracts_file: str | Path, capabilities_file: str | Path) -> None:
        raw = yaml.safe_load(Path(contracts_file).read_text(encoding="utf-8")) or {}
        version = str(raw.get("version") or "")
        if version != "xa-guard-tool-effects/v2":
            raise ContractError("strict reference deployments require xa-guard-tool-effects/v2")
        self.contracts: dict[str, EffectContractV2] = {}
        for tool_name, spec in dict(raw.get("tools") or {}).items():
            normalized = {"tool_name": tool_name, **dict(spec)}
            declared_hash = str(normalized.pop("contract_hash", ""))
            actual_hash = sha256_json(normalized)
            if declared_hash and declared_hash != actual_hash:
                raise ContractError(f"contract hash mismatch for {tool_name}")
            retry = normalized.get("retry") or {}
            success = normalized.get("success") or {}
            self.contracts[tool_name] = EffectContractV2(
                tool_name=tool_name,
                contract_version=str(normalized.get("contract_version") or "2"),
                contract_hash=actual_hash,
                success_pointer=str(success.get("pointer") or "$result#/ok"),
                success_equals=success.get("equals", True),
                side_effect_level=str(normalized.get("side_effect_level") or "high"),
                reversibility=str(normalized.get("reversibility") or "manual_required"),
                undo_window_seconds=int(normalized.get("undo_window_seconds") or 0),
                recovery_fields=dict(normalized.get("recovery_fields") or {}),
                compensation_tool=str(normalized.get("compensation_tool") or normalized.get("undo_tool") or ""),
                compensation_arguments=dict(normalized.get("compensation_arguments") or normalized.get("undo_arguments") or {}),
                idempotency_header=str((normalized.get("idempotency") or {}).get("header") or "Idempotency-Key"),
                reconciliation_method=str(normalized.get("reconciliation_method") or ""),
                retry_delays_seconds=tuple(int(v) for v in retry.get("delays_seconds", [5, 30, 120])),
            )
        caps = yaml.safe_load(Path(capabilities_file).read_text(encoding="utf-8")) or {}
        self.write_tools = {
            str(item.get("tool_name") or "")
            for item in caps.get("tools", [])
            if self.WRITE_CAPABILITIES.intersection(set(item.get("capabilities") or []))
        }

    def for_tool(self, tool_name: str) -> EffectContractV2 | None:
        contract = self.contracts.get(tool_name)
        if tool_name in self.write_tools and contract is None:
            raise ContractError(f"write tool {tool_name} has no v2 side-effect contract")
        return contract


def resolve_pointer(root: dict[str, Any], expression: str) -> Any:
    if not expression.startswith("$") or "#/" not in expression:
        raise ContractError(f"invalid contract pointer: {expression}")
    section, pointer = expression[1:].split("#/", 1)
    value: Any = root.get(section)
    for part in pointer.split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(value, dict) or part not in value:
            raise ContractError(f"contract pointer did not resolve: {expression}")
        value = value[part]
    return value


def contract_succeeded(contract: EffectContractV2, result: Any) -> bool:
    try:
        return resolve_pointer({"result": result}, contract.success_pointer) == contract.success_equals
    except ContractError:
        return False

