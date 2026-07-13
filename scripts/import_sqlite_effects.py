"""Import public legacy SQLite effect metadata into the PostgreSQL control plane.

The legacy store encrypted recovery material directly with one AES key.  The
PostgreSQL store uses a random DEK per effect, wrapped by a versioned KEK.  This
tool deliberately never selects, decrypts, or imports the legacy nonce,
ciphertext, or key identifier.  Every imported effect is therefore marked
``manual_required``.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sqlite3
import sys
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DATABASE_ENV = "XA_GUARD_DATABASE_URL"
LEGACY_CONTRACT_VERSION = "legacy-sqlite/v1"
MIGRATION_LOCK_ID = 0x58414744
MANUAL_ERROR_CODE = "legacy_recovery_format_incompatible"
IMPORTED_EVENT_TYPE = "legacy_effect_event_imported"

_EFFECT_COLUMNS = {
    "effect_id",
    "tenant_id",
    "trace_id",
    "principal",
    "agent_id",
    "data_domain",
    "tool_name",
    "side_effect_level",
    "reversibility",
    "undo_tool",
    "status",
    "result_sha256",
    "compensation_trace_id",
}
_EVENT_COLUMNS = {
    "seq",
    "effect_id",
    "event_type",
    "actor",
    "payload_json",
    "prev_hash",
    "record_hash",
}
_PUBLIC_EVENT_PAYLOAD_KEYS = {"trace_id", "request_id", "reason_sha256"}


class ImportFailure(RuntimeError):
    """An expected source validation or target import failure."""


@dataclass(frozen=True)
class LegacyEffect:
    effect_id: str
    tenant_id: str
    trace_id: str
    principal: str
    agent_id: str
    data_domain: str
    tool_name: str
    side_effect_level: str
    reversibility: str
    undo_tool: str
    status: str
    result_sha256: str
    compensation_trace_id: str


@dataclass(frozen=True)
class LegacyEvent:
    seq: int
    effect_id: str
    event_type: str
    actor: str
    public_payload: dict[str, str]
    payload_was_valid: bool
    prev_hash: str
    record_hash: str


@dataclass(frozen=True)
class LegacySnapshot:
    effects: tuple[LegacyEffect, ...]
    events: tuple[LegacyEvent, ...]


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _text(row: sqlite3.Row, column: str) -> str:
    value = row[column]
    return "" if value is None else str(value)


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}


def _require_columns(conn: sqlite3.Connection, table: str, required: set[str]) -> None:
    columns = _table_columns(conn, table)
    missing = sorted(required - columns)
    if missing:
        raise ImportFailure(f"legacy table {table!r} is absent or missing required public columns")


def _public_event_payload(raw: str) -> tuple[dict[str, str], bool]:
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}, False
    if not isinstance(value, dict):
        return {}, False
    public: dict[str, str] = {}
    for key in _PUBLIC_EVENT_PAYLOAD_KEYS:
        item = value.get(key)
        if isinstance(item, str):
            public[key] = item
    return public, True


def read_legacy_snapshot(path: Path) -> LegacySnapshot:
    if not path.is_file():
        raise ImportFailure("legacy SQLite database is absent or is not a regular file")
    uri = path.resolve().as_uri() + "?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=5)
    except sqlite3.Error as exc:
        raise ImportFailure("legacy SQLite database could not be opened read-only") from exc

    with closing(conn):
        conn.row_factory = sqlite3.Row
        try:
            _require_columns(conn, "effects", _EFFECT_COLUMNS)
            _require_columns(conn, "effect_events", _EVENT_COLUMNS)
            # Deliberately omit nonce, recovery_ciphertext, and key_id.  Keeping
            # them out of the SELECT makes the no-recovery boundary auditable.
            effect_rows = conn.execute(
                """
                SELECT effect_id,tenant_id,trace_id,principal,agent_id,data_domain,tool_name,
                       side_effect_level,reversibility,undo_tool,status,result_sha256,
                       compensation_trace_id
                  FROM effects ORDER BY rowid
                """
            ).fetchall()
            event_rows = conn.execute(
                """
                SELECT seq,effect_id,event_type,actor,payload_json,prev_hash,record_hash
                  FROM effect_events ORDER BY seq
                """
            ).fetchall()
        except sqlite3.Error as exc:
            raise ImportFailure("legacy public effect metadata could not be read") from exc

    effects = tuple(
        LegacyEffect(
            effect_id=_text(row, "effect_id"),
            tenant_id=_text(row, "tenant_id"),
            trace_id=_text(row, "trace_id"),
            principal=_text(row, "principal"),
            agent_id=_text(row, "agent_id"),
            data_domain=_text(row, "data_domain"),
            tool_name=_text(row, "tool_name"),
            side_effect_level=_text(row, "side_effect_level"),
            reversibility=_text(row, "reversibility"),
            undo_tool=_text(row, "undo_tool"),
            status=_text(row, "status"),
            result_sha256=_text(row, "result_sha256"),
            compensation_trace_id=_text(row, "compensation_trace_id"),
        )
        for row in effect_rows
    )
    events: list[LegacyEvent] = []
    for row in event_rows:
        public_payload, valid = _public_event_payload(_text(row, "payload_json"))
        events.append(
            LegacyEvent(
                seq=int(row["seq"]),
                effect_id=_text(row, "effect_id"),
                event_type=_text(row, "event_type"),
                actor=_text(row, "actor"),
                public_payload=public_payload,
                payload_was_valid=valid,
                prev_hash=_text(row, "prev_hash"),
                record_hash=_text(row, "record_hash"),
            )
        )
    return LegacySnapshot(effects=effects, events=tuple(events))


def _legacy_contract(effect: LegacyEffect) -> tuple[dict[str, Any], str]:
    contract = {
        "tool_name": effect.tool_name,
        "contract_version": LEGACY_CONTRACT_VERSION,
        "side_effect_level": effect.side_effect_level,
        "reversibility": "manual_required",
        "undo_window_seconds": 0,
        "recovery_fields": {},
        "compensation_tool": "",
        "compensation_arguments": {},
        "idempotency_header": "",
        "reconciliation_method": "",
        "retry_delays_seconds": [],
        "legacy": {
            "status": effect.status,
            "reversibility": effect.reversibility,
            "undo_tool": effect.undo_tool,
            "recovery_imported": False,
        },
    }
    contract_hash = _sha256_json(contract)
    return {**contract, "contract_hash": contract_hash}, contract_hash


async def _verify_target_schema(conn: Any) -> None:
    effects = await conn.fetchval("SELECT to_regclass('public.xa_effects')")
    events = await conn.fetchval("SELECT to_regclass('public.xa_effect_events')")
    versions = await conn.fetchval("SELECT to_regclass('public.xa_schema_versions')")
    if not effects or not events or not versions:
        raise ImportFailure("target control-plane migrations have not been applied")
    version = await conn.fetchval("SELECT COALESCE(max(version),0) FROM xa_schema_versions")
    if int(version or 0) < 1:
        raise ImportFailure("target control-plane schema version is too old")


async def _insert_effect(conn: Any, effect: LegacyEffect) -> bool:
    snapshot, contract_hash = _legacy_contract(effect)
    inserted = await conn.fetchval(
        """
        INSERT INTO xa_effects(
          effect_id,tenant_id,trace_id,principal_sub,principal_username,agent_id,data_domain,
          tool_name,args_sha256,contract_version,contract_hash,contract_snapshot,side_effect_level,
          reversibility,status,prepared_at,completed_at,undo_expires_at,result_sha256,
          compensation_trace_id,last_error_code,updated_at)
        VALUES($1,$2,$3,$4,$4,$5,$6,$7,'',$8,$9,$10::jsonb,$11,
               'manual_required','manual_required',now(),now(),now(),$12,$13,$14,now())
        ON CONFLICT (effect_id) DO NOTHING
        RETURNING effect_id
        """,
        effect.effect_id,
        effect.tenant_id,
        effect.trace_id,
        effect.principal,
        effect.agent_id,
        effect.data_domain,
        effect.tool_name,
        LEGACY_CONTRACT_VERSION,
        contract_hash,
        json.dumps(snapshot, ensure_ascii=False, sort_keys=True),
        effect.side_effect_level,
        effect.result_sha256,
        effect.compensation_trace_id,
        MANUAL_ERROR_CODE,
    )
    return inserted is not None


async def _is_compatible_existing_effect(conn: Any, effect: LegacyEffect) -> bool:
    row = await conn.fetchrow(
        "SELECT tenant_id,contract_version FROM xa_effects WHERE effect_id=$1",
        effect.effect_id,
    )
    return bool(
        row
        and str(row["tenant_id"]) == effect.tenant_id
        and str(row["contract_version"]) == LEGACY_CONTRACT_VERSION
    )


async def _insert_event(conn: Any, tenant_id: str, event: LegacyEvent) -> bool:
    already_present = await conn.fetchval(
        """
        SELECT EXISTS(
          SELECT 1 FROM xa_effect_events
           WHERE tenant_id=$1 AND effect_id=$2 AND event_type=$3
             AND payload->>'legacy_seq'=$4
             AND payload->>'legacy_record_hash'=$5
        )
        """,
        tenant_id,
        event.effect_id,
        IMPORTED_EVENT_TYPE,
        str(event.seq),
        event.record_hash,
    )
    if already_present:
        return False

    await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", f"effect-chain:{tenant_id}")
    prev_hash = (
        await conn.fetchval(
            "SELECT record_hash FROM xa_effect_events WHERE tenant_id=$1 ORDER BY seq DESC LIMIT 1",
            tenant_id,
        )
        or ""
    )
    payload = {
        "legacy_seq": event.seq,
        "legacy_event_type": event.event_type,
        "legacy_prev_hash": event.prev_hash,
        "legacy_record_hash": event.record_hash,
        "legacy_public_payload": event.public_payload,
    }
    value = {
        "tenant_id": tenant_id,
        "effect_id": event.effect_id,
        "event_type": IMPORTED_EVENT_TYPE,
        "actor_sub": event.actor,
        "payload": payload,
        "prev_hash": prev_hash,
    }
    inserted = await conn.fetchval(
        """
        INSERT INTO xa_effect_events(
          tenant_id,effect_id,event_type,actor_sub,payload,prev_hash,record_hash)
        VALUES($1,$2,$3,$4,$5::jsonb,$6,$7)
        ON CONFLICT DO NOTHING
        RETURNING seq
        """,
        tenant_id,
        event.effect_id,
        IMPORTED_EVENT_TYPE,
        event.actor,
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        prev_hash,
        _sha256_json(value),
    )
    return inserted is not None


async def import_snapshot(snapshot: LegacySnapshot, dsn: str) -> dict[str, int | bool]:
    try:
        import asyncpg
    except ImportError as exc:
        raise ImportFailure("asyncpg is required for a non-dry-run import") from exc

    try:
        conn = await asyncpg.connect(dsn, command_timeout=30)
    except Exception as exc:
        raise ImportFailure("target PostgreSQL connection failed") from exc

    stats: dict[str, int | bool] = {
        "dry_run": False,
        "effects_scanned": len(snapshot.effects),
        "effects_inserted": 0,
        "effects_existing": 0,
        "effects_conflicted": 0,
        "events_scanned": len(snapshot.events),
        "events_inserted": 0,
        "events_existing": 0,
        "events_skipped": 0,
        "event_payloads_invalid": sum(not event.payload_was_valid for event in snapshot.events),
    }
    locked = False
    try:
        await conn.execute("SELECT pg_advisory_lock($1)", MIGRATION_LOCK_ID)
        locked = True
        await _verify_target_schema(conn)
        effect_by_id = {effect.effect_id: effect for effect in snapshot.effects}
        effect_tenant_by_id = {effect.effect_id: effect.tenant_id for effect in snapshot.effects}
        eligible_effects: set[str] = set()
        async with conn.transaction():
            for effect in snapshot.effects:
                if await _insert_effect(conn, effect):
                    stats["effects_inserted"] += 1
                    eligible_effects.add(effect.effect_id)
                elif await _is_compatible_existing_effect(conn, effect):
                    stats["effects_existing"] += 1
                    eligible_effects.add(effect.effect_id)
                else:
                    stats["effects_conflicted"] += 1

            ordered_events = sorted(
                snapshot.events,
                key=lambda item: (
                    effect_tenant_by_id.get(item.effect_id, ""),
                    item.seq,
                ),
            )
            for event in ordered_events:
                effect = effect_by_id.get(event.effect_id)
                if effect is None or event.effect_id not in eligible_effects:
                    stats["events_skipped"] += 1
                    continue
                if await _insert_event(conn, effect.tenant_id, event):
                    stats["events_inserted"] += 1
                else:
                    stats["events_existing"] += 1
    except ImportFailure:
        raise
    except Exception as exc:
        raise ImportFailure("target PostgreSQL import failed") from exc
    finally:
        if locked:
            try:
                await conn.execute("SELECT pg_advisory_unlock($1)", MIGRATION_LOCK_ID)
            except Exception:
                pass
        await conn.close()
    return stats


def _read_database_url(args: argparse.Namespace) -> str:
    direct = args.database_url or os.getenv(DATABASE_ENV, "").strip()
    file_name = args.database_url_file or os.getenv(DATABASE_ENV + "_FILE", "").strip()
    if direct:
        return direct
    if not file_name:
        raise ImportFailure(
            f"target DSN is absent; use --database-url, --database-url-file, {DATABASE_ENV}, or {DATABASE_ENV}_FILE"
        )
    try:
        value = Path(file_name).read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ImportFailure("target DSN file could not be read") from exc
    if not value:
        raise ImportFailure("target DSN file is empty")
    return value


def _dry_run_stats(snapshot: LegacySnapshot) -> dict[str, int | bool]:
    effect_ids = {effect.effect_id for effect in snapshot.effects}
    return {
        "dry_run": True,
        "effects_scanned": len(snapshot.effects),
        "effects_manual_required": len(snapshot.effects),
        "events_scanned": len(snapshot.events),
        "events_eligible": sum(event.effect_id in effect_ids for event in snapshot.events),
        "events_skipped": sum(event.effect_id not in effect_ids for event in snapshot.events),
        "event_payloads_invalid": sum(not event.payload_was_valid for event in snapshot.events),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Import public legacy SQLite effect/event metadata into PostgreSQL. "
            "Recovery ciphertext is never read; imported effects become manual_required."
        )
    )
    parser.add_argument(
        "--sqlite", required=True, type=Path, help="Path to the legacy effects SQLite database"
    )
    dsn = parser.add_mutually_exclusive_group()
    dsn.add_argument("--database-url", help="Target PostgreSQL DSN (prefer --database-url-file)")
    dsn.add_argument("--database-url-file", help="File containing the target PostgreSQL DSN")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and count source rows without reading a target DSN or connecting to PostgreSQL",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        snapshot = read_legacy_snapshot(args.sqlite)
        if args.dry_run:
            stats = _dry_run_stats(snapshot)
        else:
            stats = asyncio.run(import_snapshot(snapshot, _read_database_url(args)))
    except ImportFailure as exc:
        print(f"import failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(stats, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
