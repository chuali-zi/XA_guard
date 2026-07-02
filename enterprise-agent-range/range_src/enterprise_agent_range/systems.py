from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .io_utils import sha256_text, stable_json_dumps, utc_now_iso
from .models import REQUIRED_AUDIT_FIELDS
from .sensitive import find_sensitive_hits


@dataclass
class RangeState:
    run_id: str
    sut_id: str
    environment_hash: str
    manifest_root: Path
    side_effects: list[dict[str, Any]] = field(default_factory=list)
    audit_records: list[dict[str, Any]] = field(default_factory=list)
    service_state: dict[str, dict[str, Any]] = field(default_factory=dict)
    trace_context: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    _audit_prev_hash: str = "sha256:0"

    def record_side_effect(
        self,
        trace_id: str,
        sink_type: str,
        operation: str,
        payload: Any,
        committed: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        row = {
            "trace_id": trace_id,
            "sink_type": sink_type,
            "operation": operation,
            "payload_hash": sha256_text(stable_json_dumps(payload)),
            "sensitive_hits": find_sensitive_hits(payload),
            "committed": committed,
            "metadata": metadata or {},
        }
        self.side_effects.append(row)
        return row

    def record_audit(
        self,
        *,
        trace_id: str,
        case_id: str,
        principal_id: str,
        agent_id: str,
        tool_name: str,
        decision: str,
        reason: str,
        input_payload: Any,
        output_payload: Any,
        downstream_effect: Any,
    ) -> dict[str, Any]:
        row = {
            "trace_id": trace_id,
            "case_id": case_id,
            "principal_id": principal_id,
            "agent_id": agent_id,
            "tool_name": tool_name,
            "decision": decision,
            "reason": reason,
            "input_hash": sha256_text(stable_json_dumps(input_payload)),
            "output_hash": sha256_text(stable_json_dumps(output_payload)),
            "downstream_effect_hash": sha256_text(stable_json_dumps(downstream_effect)),
            "timestamp": utc_now_iso(),
            "sut_id": self.sut_id,
            "environment_hash": self.environment_hash,
            "prev_hash": self._audit_prev_hash,
        }
        row["record_hash"] = sha256_text(stable_json_dumps(row))
        self._audit_prev_hash = row["record_hash"]
        self.audit_records.append(row)
        return row

    def remember_context(self, trace_id: str, tool_name: str, output: dict[str, Any]) -> None:
        self.trace_context.setdefault(trace_id, []).append(
            {
                "tool_name": tool_name,
                "output": output,
            }
        )

    def context_for_trace(self, trace_id: str) -> list[dict[str, Any]]:
        return list(self.trace_context.get(trace_id, []))

    @property
    def audit_prev_hash(self) -> str:
        return self._audit_prev_hash


@dataclass(frozen=True)
class ToolContext:
    state: RangeState
    case: dict[str, Any]
    trace_id: str

    @property
    def case_id(self) -> str:
        return str(self.case.get("case_id"))

    @property
    def principal_id(self) -> str:
        return str(self.case.get("principal", {}).get("principal_id", "unknown"))

    @property
    def agent_id(self) -> str:
        return str(self.case.get("agent", {}).get("agent_id", "unknown"))


def verify_audit_chain(records: list[dict[str, Any]], start_hash: str = "sha256:0") -> bool:
    previous = start_hash
    for record in records:
        missing = REQUIRED_AUDIT_FIELDS - set(record)
        if missing:
            return False
        observed_hash = record.get("record_hash")
        if record.get("prev_hash") != previous:
            return False
        candidate = dict(record)
        candidate.pop("record_hash", None)
        if sha256_text(stable_json_dumps(candidate)) != observed_hash:
            return False
        previous = str(observed_hash)
    return True


def audit_completeness(records: list[dict[str, Any]]) -> tuple[int, int]:
    expected = len(records) * len(REQUIRED_AUDIT_FIELDS)
    present = 0
    for record in records:
        present += len(REQUIRED_AUDIT_FIELDS & set(record))
    return present, expected
