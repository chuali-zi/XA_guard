"""Encrypted SQLite EffectStore used only by the round-2 feasibility experiment."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


SCHEMA_VERSION = "xa-guard-effect-store-feasibility/v0.1"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


class EffectStoreError(RuntimeError):
    pass


class RecoveryDecryptError(EffectStoreError):
    pass


@dataclass(frozen=True)
class DurableEffect:
    effect_id: str
    tenant_id: str
    trace_id: str
    principal: str
    agent_id: str
    tool_name: str
    reversibility: str
    before_sha256: str
    after_sha256: str
    status: str = "available"


@dataclass(frozen=True)
class ClaimResult:
    claimed: bool
    reason: str
    effect_id: str = ""


class EncryptedEffectStore:
    """Small durable state machine with encrypted recovery material and hashed events."""

    def __init__(self, path: str | Path, *, key: bytes, key_id: str | None = None) -> None:
        if len(key) != 32:
            raise ValueError("round-2 EffectStore requires a 256-bit AES key")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.key = bytes(key)
        self.key_id = key_id or f"aes256-{hashlib.sha256(self.key).hexdigest()[:16]}"
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS effects (
                    effect_id TEXT PRIMARY KEY,
                    schema_version TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    trace_id TEXT NOT NULL,
                    principal TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    reversibility TEXT NOT NULL,
                    before_sha256 TEXT NOT NULL,
                    after_sha256 TEXT NOT NULL,
                    status TEXT NOT NULL,
                    nonce BLOB NOT NULL,
                    recovery_ciphertext BLOB NOT NULL,
                    key_id TEXT NOT NULL,
                    compensation_trace_id TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS undo_requests (
                    request_id TEXT PRIMARY KEY,
                    effect_id TEXT NOT NULL REFERENCES effects(effect_id),
                    idempotency_key TEXT NOT NULL UNIQUE,
                    requester TEXT NOT NULL,
                    approver TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    effect_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    prev_hash TEXT NOT NULL,
                    record_hash TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def _aad(effect: DurableEffect | sqlite3.Row) -> bytes:
        return _canonical(
            {
                "schema_version": SCHEMA_VERSION,
                "effect_id": effect["effect_id"] if isinstance(effect, sqlite3.Row) else effect.effect_id,
                "tenant_id": effect["tenant_id"] if isinstance(effect, sqlite3.Row) else effect.tenant_id,
                "tool_name": effect["tool_name"] if isinstance(effect, sqlite3.Row) else effect.tool_name,
            }
        )

    def create_effect(self, effect: DurableEffect, recovery_material: dict[str, Any]) -> None:
        nonce = os.urandom(12)
        ciphertext = AESGCM(self.key).encrypt(nonce, _canonical(recovery_material), self._aad(effect))
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                INSERT INTO effects (
                    effect_id, schema_version, tenant_id, trace_id, principal, agent_id,
                    tool_name, reversibility, before_sha256, after_sha256, status,
                    nonce, recovery_ciphertext, key_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    effect.effect_id,
                    SCHEMA_VERSION,
                    effect.tenant_id,
                    effect.trace_id,
                    effect.principal,
                    effect.agent_id,
                    effect.tool_name,
                    effect.reversibility,
                    effect.before_sha256,
                    effect.after_sha256,
                    effect.status,
                    nonce,
                    ciphertext,
                    self.key_id,
                ),
            )
            self._append_event(
                conn,
                effect_id=effect.effect_id,
                event_type="effect_recorded",
                actor=effect.principal,
                payload={
                    "trace_id": effect.trace_id,
                    "reversibility": effect.reversibility,
                    "before_sha256": effect.before_sha256,
                    "after_sha256": effect.after_sha256,
                    "key_id": self.key_id,
                },
            )

    def get_effect(self, effect_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT effect_id, schema_version, tenant_id, trace_id, principal, agent_id,
                       tool_name, reversibility, before_sha256, after_sha256, status,
                       key_id, compensation_trace_id
                  FROM effects WHERE effect_id=?
                """,
                (effect_id,),
            ).fetchone()
        if row is None:
            raise EffectStoreError(f"unknown effect: {effect_id}")
        return dict(row)

    def decrypt_recovery(self, effect_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM effects WHERE effect_id=?", (effect_id,)).fetchone()
        if row is None:
            raise EffectStoreError(f"unknown effect: {effect_id}")
        if row["key_id"] != self.key_id:
            raise RecoveryDecryptError("recovery key id mismatch")
        try:
            plaintext = AESGCM(self.key).decrypt(
                bytes(row["nonce"]),
                bytes(row["recovery_ciphertext"]),
                self._aad(row),
            )
        except InvalidTag as exc:
            raise RecoveryDecryptError("AES-GCM authentication failed") from exc
        value = json.loads(plaintext)
        if not isinstance(value, dict):
            raise RecoveryDecryptError("recovery material is not an object")
        return value

    def request_undo(self, effect_id: str, *, requester: str, idempotency_key: str) -> tuple[str, bool]:
        request_id = f"undo-{hashlib.sha256(idempotency_key.encode('utf-8')).hexdigest()[:20]}"
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT request_id FROM undo_requests WHERE idempotency_key=?",
                (idempotency_key,),
            ).fetchone()
            if existing is not None:
                return str(existing["request_id"]), False
            effect = conn.execute("SELECT status FROM effects WHERE effect_id=?", (effect_id,)).fetchone()
            if effect is None:
                raise EffectStoreError(f"unknown effect: {effect_id}")
            if effect["status"] != "available":
                raise EffectStoreError(f"effect is not available: {effect['status']}")
            conn.execute(
                "INSERT INTO undo_requests (request_id, effect_id, idempotency_key, requester, status) "
                "VALUES (?, ?, ?, ?, 'pending')",
                (request_id, effect_id, idempotency_key, requester),
            )
            conn.execute("UPDATE effects SET status='undo_pending' WHERE effect_id=?", (effect_id,))
            self._append_event(
                conn,
                effect_id=effect_id,
                event_type="undo_requested",
                actor=requester,
                payload={"request_id": request_id, "idempotency_key_sha256": _sha256(idempotency_key)},
            )
        return request_id, True

    def claim_compensation(self, request_id: str, *, approver: str) -> ClaimResult:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            request = conn.execute(
                "SELECT * FROM undo_requests WHERE request_id=?",
                (request_id,),
            ).fetchone()
            if request is None:
                raise EffectStoreError(f"unknown undo request: {request_id}")
            if request["requester"] == approver:
                self._append_event(
                    conn,
                    effect_id=request["effect_id"],
                    event_type="undo_approval_denied",
                    actor=approver,
                    payload={"request_id": request_id, "reason": "separation_of_duty"},
                )
                return ClaimResult(False, "self_approval", str(request["effect_id"]))
            if request["status"] != "pending":
                return ClaimResult(False, f"request_{request['status']}", str(request["effect_id"]))
            changed = conn.execute(
                "UPDATE effects SET status='compensating' "
                "WHERE effect_id=? AND status='undo_pending'",
                (request["effect_id"],),
            ).rowcount
            if changed != 1:
                return ClaimResult(False, "effect_not_claimable", str(request["effect_id"]))
            conn.execute(
                "UPDATE undo_requests SET status='compensating', approver=? WHERE request_id=?",
                (approver, request_id),
            )
            self._append_event(
                conn,
                effect_id=request["effect_id"],
                event_type="compensation_started",
                actor=approver,
                payload={"request_id": request_id},
            )
            return ClaimResult(True, "claimed", str(request["effect_id"]))

    def complete_compensation(self, request_id: str, *, compensation_trace_id: str, succeeded: bool) -> None:
        effect_status = "compensated" if succeeded else "compensation_failed"
        request_status = "completed" if succeeded else "failed"
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            request = conn.execute(
                "SELECT * FROM undo_requests WHERE request_id=?",
                (request_id,),
            ).fetchone()
            if request is None or request["status"] != "compensating":
                raise EffectStoreError("undo request is not compensating")
            conn.execute(
                "UPDATE effects SET status=?, compensation_trace_id=? WHERE effect_id=?",
                (effect_status, compensation_trace_id, request["effect_id"]),
            )
            conn.execute(
                "UPDATE undo_requests SET status=? WHERE request_id=?",
                (request_status, request_id),
            )
            self._append_event(
                conn,
                effect_id=request["effect_id"],
                event_type="compensation_completed" if succeeded else "compensation_failed",
                actor=str(request["approver"]),
                payload={"request_id": request_id, "compensation_trace_id": compensation_trace_id},
            )

    def _append_event(
        self,
        conn: sqlite3.Connection,
        *,
        effect_id: str,
        event_type: str,
        actor: str,
        payload: dict[str, Any],
    ) -> None:
        previous = conn.execute("SELECT record_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        prev_hash = str(previous["record_hash"]) if previous is not None else ""
        event = {
            "effect_id": effect_id,
            "event_type": event_type,
            "actor": actor,
            "payload": payload,
            "prev_hash": prev_hash,
        }
        record_hash = hashlib.sha256(_canonical(event)).hexdigest()
        conn.execute(
            "INSERT INTO events (effect_id, event_type, actor, payload_json, prev_hash, record_hash) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                effect_id,
                event_type,
                actor,
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                prev_hash,
                record_hash,
            ),
        )

    def events(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM events ORDER BY seq").fetchall()
        return [
            {
                "seq": int(row["seq"]),
                "effect_id": str(row["effect_id"]),
                "event_type": str(row["event_type"]),
                "actor": str(row["actor"]),
                "payload": json.loads(row["payload_json"]),
                "prev_hash": str(row["prev_hash"]),
                "record_hash": str(row["record_hash"]),
            }
            for row in rows
        ]

    def verify_event_chain(self) -> bool:
        previous = ""
        for row in self.events():
            if row["prev_hash"] != previous:
                return False
            event = {
                "effect_id": row["effect_id"],
                "event_type": row["event_type"],
                "actor": row["actor"],
                "payload": row["payload"],
                "prev_hash": row["prev_hash"],
            }
            if hashlib.sha256(_canonical(event)).hexdigest() != row["record_hash"]:
                return False
            previous = row["record_hash"]
        return True

    def export_events(self, path: str | Path) -> None:
        with Path(path).open("w", encoding="utf-8", newline="\n") as handle:
            for row in self.events():
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    def checkpoint(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
