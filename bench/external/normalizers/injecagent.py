from __future__ import annotations

from typing import Any

from bench.external.provenance import record_sha256
from bench.external.schema import make_record, normalize_bool


def normalize_injecagent(raw: dict[str, Any], *, input_sha256: str, index: int) -> dict[str, Any]:
    case_id = str(raw.get("case_id") or raw.get("id") or f"injecagent-{index}")
    attack_success = normalize_bool(
        raw.get("attack_success")
        if "attack_success" in raw
        else raw.get("asr_valid")
    )
    benign_success = normalize_bool(raw.get("benign_success") or raw.get("task_success"))
    return make_record(
        benchmark_name="injecagent",
        raw=raw,
        input_sha256=input_sha256,
        input_record_index=index,
        raw_record_sha256=record_sha256(raw),
        case_id=case_id,
        task_type=raw.get("task_type") or raw.get("attack_type") or "tool_injection",
        attack_success=attack_success,
        benign_success=benign_success,
        tool_calls=raw.get("tool_calls") or raw.get("actions"),
    )
