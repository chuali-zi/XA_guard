"""Persistent pending HITL approval store.

The store keeps enough pre-approval GateContext state to let an operator resume
or reject a request after clients without elicitation support return control to
the user. Approval tokens are intentionally not stored here; they are minted at
approve time and consumed by ``Pipeline.run_after_approval``.
"""
from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from xa_guard.types import Decision, GateContext, GateResult, InputSource, RiskLevel, TaintLabel


DEFAULT_PENDING_APPROVAL_TTL_SECONDS = 300
REDACTED_ARGUMENT = "[REDACTED]"
_SENSITIVE_ARGUMENT_MARKERS = (
    "authorization",
    "cookie",
    "passwd",
    "password",
    "pwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "credential",
)


@dataclass
class PendingApproval:
    ctx: GateContext
    created_at: datetime
    expires_at: datetime
    input_schema: dict[str, Any] | None = None


def _parse_dt(value: str) -> datetime:
    text = str(value or "")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _dt(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    if normalized in _SENSITIVE_ARGUMENT_MARKERS:
        return True
    return normalized.endswith(("_key", "_secret", "_token", "_authorization", "_cookie"))


def _schema_marks_sensitive(schema: Any) -> bool:
    if not isinstance(schema, dict):
        return False
    if schema.get("x-xa-guard-sensitive") is True or schema.get("x-sensitive") is True:
        return True
    if schema.get("writeOnly") is True:
        return True
    return str(schema.get("format") or "").lower() in {"password", "secret", "token"}


def _schema_for_key(schema: Any, key: str) -> dict[str, Any] | None:
    if not isinstance(schema, dict):
        return None
    properties = schema.get("properties")
    if isinstance(properties, dict) and key in properties and isinstance(properties[key], dict):
        return properties[key]
    additional = schema.get("additionalProperties")
    if isinstance(additional, dict):
        return additional
    return None


def _schema_for_array_item(schema: Any) -> dict[str, Any] | None:
    if not isinstance(schema, dict):
        return None
    items = schema.get("items")
    return items if isinstance(items, dict) else None


def redact_arguments(value: Any, schema: dict[str, Any] | None = None) -> Any:
    """Return a ledger/listing-safe copy of tool arguments.

    Redaction is schema-aware when an MCP inputSchema is available and falls
    back to conservative key-name matching. Sensitive values are replaced by a
    marker plus a short digest, so operators can tell whether two pending
    requests carried the same secret without seeing it.
    """
    if _schema_marks_sensitive(schema):
        return f"{REDACTED_ARGUMENT}:sha256:{_digest(value)[:12]}"
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            text_key = str(key)
            child_schema = _schema_for_key(schema, text_key)
            if _schema_marks_sensitive(child_schema) or _is_sensitive_key(text_key):
                out[text_key] = f"{REDACTED_ARGUMENT}:sha256:{_digest(item)[:12]}"
            else:
                out[text_key] = redact_arguments(item, child_schema)
        return out
    if isinstance(value, list):
        item_schema = _schema_for_array_item(schema)
        return [redact_arguments(item, item_schema) for item in value]
    if isinstance(value, tuple):
        item_schema = _schema_for_array_item(schema)
        return [redact_arguments(item, item_schema) for item in value]
    return value


def arguments_are_redacted(value: Any) -> bool:
    if isinstance(value, dict):
        return any(arguments_are_redacted(item) for item in value.values())
    if isinstance(value, list):
        return any(arguments_are_redacted(item) for item in value)
    if isinstance(value, str):
        return value.startswith(REDACTED_ARGUMENT)
    return False


def _redact_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in (metadata or {}).items():
        if _is_sensitive_key(str(key)):
            continue
        out[str(key)] = value
    return out


def gate_result_to_dict(result: GateResult) -> dict[str, Any]:
    return {
        "gate_name": result.gate_name,
        "decision": result.decision.value,
        "risks": list(result.risks),
        "rule_hits": list(result.rule_hits),
        "metadata": _redact_metadata(result.metadata),
        "confidence": result.confidence,
        "latency_ms": result.latency_ms,
        "note": result.note,
    }


def gate_result_from_dict(raw: dict[str, Any]) -> GateResult:
    return GateResult(
        gate_name=str(raw.get("gate_name") or ""),
        decision=Decision(raw.get("decision") or Decision.ALLOW.value),
        risks=list(raw.get("risks") or []),
        rule_hits=list(raw.get("rule_hits") or []),
        metadata=dict(raw.get("metadata") or {}),
        confidence=float(raw.get("confidence", 1.0)),
        latency_ms=float(raw.get("latency_ms", 0.0)),
        note=str(raw.get("note") or ""),
    )


def context_to_dict(ctx: GateContext, input_schema: dict[str, Any] | None = None) -> dict[str, Any]:
    safe_arguments = redact_arguments(ctx.arguments, input_schema)
    return {
        "trace_id": ctx.trace_id,
        "span_id": ctx.span_id,
        "started_at": _dt(ctx.started_at),
        "tool_name": ctx.tool_name,
        "arguments": safe_arguments,
        "arguments_redacted": arguments_are_redacted(safe_arguments),
        "arguments_sha256": _digest(ctx.arguments),
        "user_role": ctx.user_role,
        "session_history": ctx.session_history,
        "input_sources": [_enum_value(item) for item in ctx.input_sources],
        "tenant_id": ctx.tenant_id,
        "human_principal": ctx.human_principal,
        "agent_id": ctx.agent_id,
        "data_domain": ctx.data_domain,
        "resource_owner": ctx.resource_owner,
        "task_id": ctx.task_id,
        "cost_estimate_usd": ctx.cost_estimate_usd,
        "output_estimate": ctx.output_estimate,
        "capability_token_summary": ctx.capability_token_summary,
        "taint": _enum_value(ctx.taint),
        "risk_level": _enum_value(ctx.risk_level),
        "gate_results": [gate_result_to_dict(item) for item in ctx.gate_results],
        "rule_hits": list(ctx.rule_hits),
        "final_decision": _enum_value(ctx.final_decision),
        "final_reason": ctx.final_reason,
    }


def context_from_dict(raw: dict[str, Any]) -> GateContext:
    ctx = GateContext(
        trace_id=str(raw.get("trace_id") or ""),
        span_id=str(raw.get("span_id") or ""),
        started_at=_parse_dt(str(raw.get("started_at"))),
        tool_name=str(raw.get("tool_name") or ""),
        arguments=dict(raw.get("arguments") or {}),
        user_role=str(raw.get("user_role") or "user"),
        session_history=list(raw.get("session_history") or []),
        input_sources=[
            InputSource(item) for item in (raw.get("input_sources") or [InputSource.USER.value])
        ],
        tenant_id=str(raw.get("tenant_id") or ""),
        human_principal=str(raw.get("human_principal") or ""),
        agent_id=str(raw.get("agent_id") or ""),
        data_domain=str(raw.get("data_domain") or ""),
        resource_owner=str(raw.get("resource_owner") or ""),
        task_id=str(raw.get("task_id") or ""),
        cost_estimate_usd=float(raw.get("cost_estimate_usd") or 0.0),
        output_estimate=str(raw.get("output_estimate") or ""),
        capability_token_summary=dict(raw.get("capability_token_summary") or {}),
    )
    ctx.taint = TaintLabel(raw.get("taint") or TaintLabel.PUBLIC.value)
    ctx.risk_level = RiskLevel(raw.get("risk_level") or RiskLevel.GREEN.value)
    ctx.gate_results = [gate_result_from_dict(item) for item in raw.get("gate_results") or []]
    ctx.rule_hits = list(raw.get("rule_hits") or [])
    ctx.final_decision = Decision(raw.get("final_decision") or Decision.ALLOW.value)
    ctx.final_reason = str(raw.get("final_reason") or "")
    ctx.approval = None
    ctx.tool_result = None
    return ctx


class PendingApprovalStore:
    def __init__(
        self,
        *,
        ttl_seconds: int = DEFAULT_PENDING_APPROVAL_TTL_SECONDS,
        ledger_path: str | Path | None = None,
    ) -> None:
        self._ttl = timedelta(seconds=ttl_seconds)
        self._items: dict[str, PendingApproval] = {}
        self.ledger_path = Path(ledger_path) if ledger_path else None
        self._load()

    def add(self, ctx: GateContext, *, input_schema: dict[str, Any] | None = None) -> PendingApproval:
        self._prune()
        now = datetime.now(timezone.utc)
        item = PendingApproval(
            ctx=ctx,
            created_at=now,
            expires_at=now + self._ttl,
            input_schema=input_schema,
        )
        self._items[ctx.trace_id] = item
        self._append_event("pending_added", item)
        return item

    def list(self) -> list[PendingApproval]:
        self._prune()
        return list(self._items.values())

    def pop(self, trace_id: str, *, outcome: str = "consumed") -> PendingApproval | None:
        self._prune()
        item = self._items.pop(trace_id, None)
        if item is not None:
            self._append_event("pending_removed", item, outcome=outcome)
        return item

    def _load(self) -> None:
        if self.ledger_path is None or not self.ledger_path.exists():
            return
        for line in self.ledger_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                trace_id = str(event.get("trace_id") or "")
                if not trace_id:
                    continue
                if event.get("event") == "pending_added":
                    item = PendingApproval(
                        ctx=context_from_dict(dict(event.get("context") or {})),
                        created_at=_parse_dt(str(event.get("created_at"))),
                        expires_at=_parse_dt(str(event.get("expires_at"))),
                        input_schema=None,
                    )
                    if item.expires_at > datetime.now(timezone.utc):
                        self._items[trace_id] = item
                elif event.get("event") == "pending_removed":
                    self._items.pop(trace_id, None)
            except Exception:
                continue
        self._prune()

    def _prune(self) -> None:
        now = datetime.now(timezone.utc)
        expired = [trace_id for trace_id, item in self._items.items() if item.expires_at <= now]
        for trace_id in expired:
            item = self._items.pop(trace_id, None)
            if item is not None:
                self._append_event("pending_removed", item, outcome="expired")

    def _append_event(self, event: str, item: PendingApproval, *, outcome: str = "") -> None:
        if self.ledger_path is None:
            return
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "xa-guard-pending-approval-ledger/v0.1",
            "event": event,
            "trace_id": item.ctx.trace_id,
            "tool_name": item.ctx.tool_name,
            "created_at": _dt(item.created_at),
            "expires_at": _dt(item.expires_at),
            "written_at": _dt(datetime.now(timezone.utc)),
            "outcome": outcome,
        }
        if event == "pending_added":
            payload["context"] = context_to_dict(item.ctx, item.input_schema)
        with self.ledger_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
