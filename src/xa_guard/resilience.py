"""Durable, encrypted effect ledger and policy-gated compensation workflow."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

import mcp.types as mtypes
import yaml
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from xa_guard.approval import issue_approval
from xa_guard.config import ResilienceConfig
from xa_guard.identity import VerifiedIdentity
from xa_guard.types import Decision, GateContext, InputSource


class ResilienceError(RuntimeError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


@dataclass(frozen=True)
class EffectContract:
    tool_name: str
    side_effect_level: str
    reversibility: str
    recovery_fields: dict[str, str]
    undo_tool: str
    undo_arguments: dict[str, Any]


class EffectStore:
    def __init__(self, path: str | Path, key: bytes, key_id: str = "") -> None:
        if len(key) != 32:
            raise ResilienceError("recovery key must be exactly 256 bits")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.key = key
        self.key_id = key_id or f"aes256-{hashlib.sha256(key).hexdigest()[:16]}"
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS effects (
              effect_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, trace_id TEXT NOT NULL,
              principal TEXT NOT NULL, agent_id TEXT NOT NULL, data_domain TEXT NOT NULL, tool_name TEXT NOT NULL,
              side_effect_level TEXT NOT NULL, reversibility TEXT NOT NULL, undo_tool TEXT NOT NULL,
              status TEXT NOT NULL, nonce BLOB NOT NULL, recovery_ciphertext BLOB NOT NULL,
              key_id TEXT NOT NULL, result_sha256 TEXT NOT NULL, compensation_trace_id TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS undo_requests (
              request_id TEXT PRIMARY KEY, effect_id TEXT NOT NULL REFERENCES effects(effect_id),
              idempotency_key TEXT NOT NULL UNIQUE, requester TEXT NOT NULL, reason TEXT NOT NULL,
              approver TEXT NOT NULL DEFAULT '', status TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS effect_events (
              seq INTEGER PRIMARY KEY AUTOINCREMENT, effect_id TEXT NOT NULL, event_type TEXT NOT NULL,
              actor TEXT NOT NULL, payload_json TEXT NOT NULL, prev_hash TEXT NOT NULL, record_hash TEXT NOT NULL
            );
            """)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _aad(self, effect_id: str, tenant_id: str, tool_name: str) -> bytes:
        return _canonical({"effect_id": effect_id, "tenant_id": tenant_id, "tool_name": tool_name})

    def create(self, *, ctx: GateContext, contract: EffectContract, recovery: dict[str, Any], result: Any) -> str:
        effect_id = f"eff-{uuid.uuid4().hex}"
        nonce = os.urandom(12)
        ciphertext = AESGCM(self.key).encrypt(nonce, _canonical(recovery), self._aad(effect_id, ctx.tenant_id, ctx.tool_name))
        initial_status = "available" if contract.reversibility == "compensatable" and contract.undo_tool else "manual_required"
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO effects VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (effect_id, ctx.tenant_id, ctx.trace_id, ctx.human_principal, ctx.agent_id,
                 ctx.data_domain, ctx.tool_name, contract.side_effect_level, contract.reversibility, contract.undo_tool,
                 initial_status, nonce, ciphertext, self.key_id, _digest(result), ""),
            )
            self._event(conn, effect_id, "effect_recorded", ctx.human_principal, {"trace_id": ctx.trace_id, "key_id": self.key_id})
        return effect_id

    def list_effects(self, tenant_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT effect_id,tenant_id,trace_id,principal,agent_id,data_domain,tool_name,side_effect_level,reversibility,status,result_sha256,compensation_trace_id FROM effects WHERE tenant_id=? ORDER BY rowid DESC LIMIT ?",
                (tenant_id, max(1, min(limit, 200))),
            ).fetchall()
        return [dict(row) for row in rows]

    def request(self, effect_id: str, requester: str, reason: str, idempotency_key: str, tenant_id: str) -> tuple[str, bool]:
        request_id = f"undo-{hashlib.sha256(idempotency_key.encode()).hexdigest()[:20]}"
        idempotency_digest = hashlib.sha256(idempotency_key.encode()).hexdigest()
        reason_digest = _digest(reason)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            old = conn.execute("SELECT request_id FROM undo_requests WHERE idempotency_key=?", (idempotency_digest,)).fetchone()
            if old:
                return str(old["request_id"]), False
            effect = conn.execute("SELECT status,tenant_id FROM effects WHERE effect_id=?", (effect_id,)).fetchone()
            if effect is None or effect["tenant_id"] != tenant_id:
                raise ResilienceError("effect not found in requester's tenant")
            if effect["status"] != "available":
                raise ResilienceError(f"effect is not undoable: {effect['status']}")
            conn.execute("INSERT INTO undo_requests VALUES (?,?,?,?,?,'','pending')", (request_id, effect_id, idempotency_digest, requester, reason_digest))
            conn.execute("UPDATE effects SET status='undo_pending' WHERE effect_id=?", (effect_id,))
            self._event(conn, effect_id, "undo_requested", requester, {"request_id": request_id, "reason_sha256": _digest(reason)})
        return request_id, True

    def claim(self, request_id: str, approver: str, tenant_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT r.*,e.tenant_id,e.data_domain,e.tool_name,e.undo_tool,e.nonce,e.recovery_ciphertext,e.key_id FROM undo_requests r JOIN effects e ON e.effect_id=r.effect_id WHERE r.request_id=?", (request_id,)).fetchone()
            if row is None or row["tenant_id"] != tenant_id:
                raise ResilienceError("undo request not found in approver's tenant")
            if row["requester"] == approver:
                raise ResilienceError("separation of duty forbids self-approval")
            changed = conn.execute("UPDATE effects SET status='compensating' WHERE effect_id=? AND status='undo_pending'", (row["effect_id"],)).rowcount
            if row["status"] != "pending" or changed != 1:
                raise ResilienceError("undo request was already claimed")
            conn.execute("UPDATE undo_requests SET status='compensating',approver=? WHERE request_id=?", (approver, request_id))
            self._event(conn, row["effect_id"], "compensation_started", approver, {"request_id": request_id})
            return dict(row)

    def decrypt(self, row: dict[str, Any]) -> dict[str, Any]:
        if row["key_id"] != self.key_id:
            raise ResilienceError("recovery key id mismatch")
        try:
            raw = AESGCM(self.key).decrypt(bytes(row["nonce"]), bytes(row["recovery_ciphertext"]), self._aad(row["effect_id"], row["tenant_id"], row["tool_name"]))
        except InvalidTag as exc:
            raise ResilienceError("recovery material authentication failed") from exc
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ResilienceError("invalid recovery material")
        return value

    def complete(self, request_id: str, trace_id: str, success: bool) -> None:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            req = conn.execute("SELECT * FROM undo_requests WHERE request_id=?", (request_id,)).fetchone()
            if req is None or req["status"] != "compensating":
                raise ResilienceError("undo request is not compensating")
            status = "compensated" if success else "compensation_failed"
            conn.execute("UPDATE effects SET status=?,compensation_trace_id=? WHERE effect_id=?", (status, trace_id, req["effect_id"]))
            conn.execute("UPDATE undo_requests SET status=? WHERE request_id=?", ("completed" if success else "failed", request_id))
            self._event(conn, req["effect_id"], status, req["approver"], {"request_id": request_id, "trace_id": trace_id})

    def _event(self, conn: sqlite3.Connection, effect_id: str, kind: str, actor: str, payload: dict[str, Any]) -> None:
        prior = conn.execute("SELECT record_hash FROM effect_events ORDER BY seq DESC LIMIT 1").fetchone()
        prev = str(prior[0]) if prior else ""
        value = {"effect_id": effect_id, "event_type": kind, "actor": actor, "payload": payload, "prev_hash": prev}
        conn.execute("INSERT INTO effect_events(effect_id,event_type,actor,payload_json,prev_hash,record_hash) VALUES(?,?,?,?,?,?)", (effect_id, kind, actor, json.dumps(payload, ensure_ascii=False, sort_keys=True), prev, _digest(value)))


class ResilienceManager:
    def __init__(self, cfg: ResilienceConfig) -> None:
        self.cfg = cfg
        raw = yaml.safe_load(Path(cfg.contracts_file).read_text(encoding="utf-8")) or {}
        source = raw.get("tools", raw)
        self.contracts = {
            name: EffectContract(name, str(v["side_effect_level"]), str(v["reversibility"]), dict(v.get("recovery_fields") or {}), str(v.get("undo_tool") or ""), dict(v.get("undo_arguments") or {}))
            for name, v in source.items()
        }
        key_text = os.getenv(cfg.key_env, "")
        if not key_text:
            raise ResilienceError(f"encrypted effect store key is absent: {cfg.key_env}")
        try:
            key = base64.b64decode(key_text, validate=True)
        except (ValueError, binascii.Error):
            try:
                key = bytes.fromhex(key_text)
            except ValueError as exc:
                raise ResilienceError("recovery key must be base64 or hex") from exc
        self.store = EffectStore(cfg.store_path, key, cfg.key_id)

    async def execute(self, ctx: GateContext, executor: Callable[[GateContext], Awaitable[Any]]) -> Any:
        result = await executor(ctx)
        contract = self.contracts.get(ctx.tool_name)
        if contract is None or ctx.operation_kind != "forward":
            return result
        payload = _payload(result)
        if isinstance(payload, dict) and payload.get("ok") is False:
            return result
        recovery = {name: _pointer({"input": ctx.arguments, "result": payload}, expr) for name, expr in contract.recovery_fields.items()}
        ctx.effect_id = self.store.create(ctx=ctx, contract=contract, recovery=recovery, result=payload)
        ctx.side_effect_level = contract.side_effect_level
        ctx.reversibility = contract.reversibility
        ctx.undo_status = "available" if contract.reversibility == "compensatable" and contract.undo_tool else "manual_required"
        return result

    def request_undo(self, identity: VerifiedIdentity, args: dict[str, Any]) -> dict[str, Any]:
        if "undo.request" not in identity.permissions:
            raise ResilienceError("identity lacks undo.request permission")
        effect_id = str(args.get("effect_id") or "").strip()
        reason = str(args.get("reason") or "").strip()
        idempotency_key = str(args.get("idempotency_key") or "").strip()
        if not effect_id or not reason or not idempotency_key:
            raise ResilienceError("effect_id, reason and idempotency_key are required")
        request_id, created = self.store.request(effect_id, identity.human_principal, reason, idempotency_key, identity.tenant_id)
        return {"request_id": request_id, "created": created, "status": "pending"}

    async def approve_undo(self, identity: VerifiedIdentity, args: dict[str, Any], pipeline: Any, executor: Callable[[GateContext], Awaitable[Any]]) -> dict[str, Any]:
        if "undo.approve" not in identity.permissions:
            raise ResilienceError("identity lacks undo.approve permission")
        request_id = str(args.get("request_id") or "")
        if not request_id or not str(args.get("reason") or "").strip():
            raise ResilienceError("request_id and approval reason are required")
        row = self.store.claim(request_id, identity.human_principal, identity.tenant_id)
        ctx = GateContext(operation_kind="compensation", compensates_effect_id=row["effect_id"])
        try:
            recovery = self.store.decrypt(row)
            contract = self.contracts[row["tool_name"]]
            values = {"recovery": recovery, "request": args}
            undo_args = {key: _pointer(values, expr) if isinstance(expr, str) and expr.startswith("$") else expr for key, expr in contract.undo_arguments.items()}
            ctx = GateContext(tool_name=contract.undo_tool, arguments=undo_args, input_sources=[InputSource.USER], tenant_id=identity.tenant_id, human_principal=identity.human_principal, agent_id=identity.agent_id, data_domain=str(row["data_domain"]), identity_verified=True, identity_issuer=identity.issuer, identity_kid=identity.kid, identity_jti_sha256=identity.jti_sha256, identity_scopes=list(identity.scopes), operation_kind="compensation", compensates_effect_id=row["effect_id"])
            result = await pipeline.run(ctx, executor)
            if result.final_decision == Decision.REQUIRE_APPROVAL:
                ctx.approval = issue_approval(trace_id=ctx.trace_id, tool_name=ctx.tool_name, arguments=ctx.arguments, approver=identity.human_principal, reason=str(args.get("reason") or "undo approved"))
                result = await pipeline.run_after_approval(ctx, executor)
            success = bool(result.allowed)
            self.store.complete(request_id, ctx.trace_id, success)
            if not success:
                raise ResilienceError(f"compensation denied: {ctx.final_reason}")
            return {"request_id": request_id, "effect_id": row["effect_id"], "status": "compensated", "compensation_trace_id": ctx.trace_id, "result": _payload(ctx.tool_result)}
        except Exception:
            try:
                self.store.complete(request_id, ctx.trace_id, False)
            except ResilienceError:
                pass
            raise


def _payload(result: Any) -> Any:
    if isinstance(result, mtypes.CallToolResult):
        if result.structuredContent is not None:
            return result.structuredContent
        texts = [block.text for block in result.content if isinstance(block, mtypes.TextContent)]
        if len(texts) == 1:
            try:
                return json.loads(texts[0])
            except ValueError:
                return texts[0]
    return result


def _pointer(root: dict[str, Any], expression: str) -> Any:
    if not expression.startswith("$") or "#/" not in expression:
        raise ResilienceError(f"invalid recovery expression: {expression}")
    section, pointer = expression[1:].split("#/", 1)
    value: Any = root.get(section)
    for part in pointer.split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            raise ResilienceError(f"recovery expression did not resolve: {expression}")
    return value
