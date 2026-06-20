from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bench.external import ADAPTER_VERSION, SCHEMA_VERSION

LIMITATIONS = [
    "adapter_only",
    "not_official_reproduction",
    "input_user_provided",
    "no_large_dependency_download",
]

REQUIRED_TOP_LEVEL = {
    "schema_version",
    "benchmark",
    "adapter",
    "case",
    "observed",
    "xa_guard_projection",
    "metrics",
    "raw_ref",
    "limitations",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def normalize_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y", "success", "attack_success"}:
            return True
        if lowered in {"false", "0", "no", "n", "fail", "failed", "attack_failed"}:
            return False
    return None


def first_present(raw: dict[str, Any], *keys: str) -> Any:
    """Return the first explicitly present field, preserving false and zero."""
    for key in keys:
        if key in raw:
            return raw[key]
    return None


def make_record(
    *,
    benchmark_name: str,
    raw: dict[str, Any],
    input_sha256: str,
    input_record_index: int,
    raw_record_sha256: str,
    case_id: str,
    task_type: str | None,
    attack_success: bool | None,
    benign_success: bool | None,
    attack_attempted: bool | None = None,
    tool_calls: list[Any] | None = None,
) -> dict[str, Any]:
    limitations = list(LIMITATIONS)
    missing = []
    for key in ("case_id", "task_type", "attack_success", "benign_success"):
        if raw.get(key) is None and key not in raw:
            missing.append(key)
    if missing:
        limitations.append("missing_fields:" + ",".join(sorted(missing)))

    first_tool_call = (tool_calls or raw.get("tool_calls") or raw.get("actions") or [None])[0]
    if not isinstance(first_tool_call, dict):
        first_tool_call = {}
    projection_tool_name = (
        raw.get("tool_name")
        or first_tool_call.get("name")
        or first_tool_call.get("tool")
        or "external_benchmark_case"
    )
    projection_arguments = (
        raw.get("arguments")
        or first_tool_call.get("arguments")
        or first_tool_call.get("args")
        or {}
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "benchmark": {
            "name": benchmark_name,
            "suite": raw.get("suite"),
            "upstream_version": raw.get("upstream_version") or raw.get("version"),
            "source_uri": raw.get("source_uri"),
            "source_commit": raw.get("source_commit") or raw.get("commit"),
            "official_claim": False,
        },
        "adapter": {
            "name": f"xa_guard.bench.external.{benchmark_name}",
            "version": ADAPTER_VERSION,
            "normalized_at": utc_now(),
            "input_sha256": input_sha256,
            "input_record_index": input_record_index,
        },
        "case": {
            "case_id": case_id,
            "task_type": task_type,
            "locale": raw.get("locale"),
            "injection_source": raw.get("injection_source") or raw.get("source"),
            "user_task": raw.get("user_task") or raw.get("task"),
            "malicious_goal": raw.get("malicious_goal") or raw.get("goal"),
            "expected_safe_behavior": raw.get("expected_safe_behavior"),
        },
        "observed": {
            "agent_name": raw.get("agent_name") or raw.get("agent"),
            "model": raw.get("model"),
            "defense": raw.get("defense"),
            "tool_calls": tool_calls or raw.get("tool_calls") or [],
            "final_response": raw.get("final_response") or raw.get("response"),
            "attack_success": attack_success,
            "benign_success": benign_success,
            "raw_label": raw.get("label") or raw.get("raw_label"),
        },
        "xa_guard_projection": {
            "input_payload": {
                "tool_name": projection_tool_name,
                "arguments": projection_arguments,
                "session_history": raw.get("session_history") or [],
            },
            "expected_decision": raw.get("expected_decision") or "deny",
            "mapping_confidence": "best_effort",
        },
        "metrics": {
            "asr_valid": attack_success,
            "asr_total": attack_attempted,
            "benign_task_success": benign_success,
            "notes": ["not_official_metric"],
        },
        "raw_ref": {
            "raw_case_id": raw.get("case_id") or raw.get("id") or case_id,
            "raw_record_sha256": raw_record_sha256,
        },
        "limitations": limitations,
    }


def validate_record(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED_TOP_LEVEL - set(record))
    if missing:
        errors.append(f"missing top-level fields: {missing}")
    if record.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"unsupported schema_version: {record.get('schema_version')}")
    if record.get("benchmark", {}).get("official_claim") is not False:
        errors.append("benchmark.official_claim must be false")
    limitations = record.get("limitations")
    if not isinstance(limitations, list) or "not_official_reproduction" not in limitations:
        errors.append("limitations must include not_official_reproduction")
    return errors
