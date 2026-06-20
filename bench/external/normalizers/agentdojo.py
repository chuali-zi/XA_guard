from __future__ import annotations

from typing import Any

from bench.external.provenance import record_sha256
from bench.external.schema import first_present, make_record, normalize_bool


def normalize_agentdojo(raw: dict[str, Any], *, input_sha256: str, index: int) -> dict[str, Any]:
    case_id = str(raw.get("case_id") or raw.get("id") or f"agentdojo-{index}")
    attack_success = normalize_bool(first_present(raw, "attack_success", "target_success"))
    benign_success = normalize_bool(first_present(raw, "benign_success", "utility_success"))
    return make_record(
        benchmark_name="agentdojo",
        raw=raw,
        input_sha256=input_sha256,
        input_record_index=index,
        raw_record_sha256=record_sha256(raw),
        case_id=case_id,
        task_type=raw.get("task_type") or raw.get("attack_type") or "indirect_prompt_injection",
        attack_success=attack_success,
        benign_success=benign_success,
        tool_calls=raw.get("tool_calls"),
    )
