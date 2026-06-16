"""Audit record completeness scoring for bench metrics and Gate6 metadata."""
from __future__ import annotations

from typing import Any

# Core OTel + hash-chain fields that Gate6 is expected to populate on every write.
CORE_AUDIT_FIELDS: tuple[str, ...] = (
    "trace_id",
    "span_id",
    "timestamp",
    "gen_ai.request.model",
    "gen_ai.usage.input_tokens",
    "gen_ai.tool.name",
    "gen_ai.tool.parameters",
    "gen_ai.tool.result.hash",
    "gen_ai.user.role",
    "gen_ai.data.sensitivity_level",
    "gen_ai.policy.hit_id",
    "gen_ai.tool.approval_token",
    "gen_ai.evidence.hash_prev",
    "gen_ai.classify.risk_tag",
    "gen_ai.decision.faithfulness_score",
    "gen_ai.decision.final",
    "gen_ai.decision.final_reason",
    "record_hash",
)

# Subset used by scripts/verify_audit.py (hash-chain smoke).
VERIFY_CHAIN_FIELDS: tuple[str, ...] = (
    "trace_id",
    "span_id",
    "timestamp",
    "gen_ai.tool.name",
    "gen_ai.tool.parameters",
    "gen_ai.tool.result.hash",
    "gen_ai.user.role",
    "gen_ai.data.sensitivity_level",
    "gen_ai.policy.hit_id",
    "gen_ai.evidence.hash_prev",
    "record_hash",
)


OPTIONAL_NULLABLE_FIELDS: frozenset[str] = frozenset(
    {
        "gen_ai.tool.approval_token",
        "gen_ai.policy.hit_id",
        "gen_ai.classify.risk_tag",
        "gen_ai.request.model",
    }
)


def _field_present(record: dict[str, Any], key: str) -> bool:
    if key not in record:
        return False
    if key in OPTIONAL_NULLABLE_FIELDS:
        return True
    value = record[key]
    if value is None:
        return False
    if key == "record_hash" and value == "":
        return False
    return True


def record_completeness_score(record: dict[str, Any], *, fields: tuple[str, ...] = CORE_AUDIT_FIELDS) -> float:
    """Return the fraction of required audit fields present on a single record."""
    if not record:
        return 0.0
    present = sum(1 for key in fields if _field_present(record, key))
    return round(present / len(fields), 4)


def is_record_complete(record: dict[str, Any], *, fields: tuple[str, ...] = CORE_AUDIT_FIELDS) -> bool:
    return record_completeness_score(record, fields=fields) >= 1.0
