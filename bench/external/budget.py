from __future__ import annotations

import json
import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


LEDGER_SCHEMA = "xa-budget-ledger/v1"


class BudgetError(RuntimeError):
    """Raised before an external call when its budget cannot be reserved."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


@contextmanager
def _file_lock(path: Path, timeout_seconds: float = 10.0) -> Iterator[None]:
    lock = path.with_suffix(path.suffix + ".lock")
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(descriptor, f"{os.getpid()}\n".encode())
            os.close(descriptor)
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise BudgetError(f"timed out acquiring budget ledger lock: {lock}")
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            lock.unlink()
        except FileNotFoundError:
            pass


def create_ledger(
    path: str | Path,
    *,
    caps: dict[str, float],
    total_cap_usd: float = 20.0,
) -> dict[str, Any]:
    ledger_path = Path(path)
    ledger = {
        "schema": LEDGER_SCHEMA,
        "created_at": _now(),
        "updated_at": _now(),
        "total_cap_usd": float(total_cap_usd),
        "bucket_caps_usd": {key: float(value) for key, value in caps.items()},
        "halted": False,
        "halt_reason": "",
        "entries": [],
    }
    with _file_lock(ledger_path):
        if ledger_path.exists():
            return load_ledger(ledger_path)
        _atomic_json(ledger_path, ledger)
    return ledger


def load_ledger(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if value.get("schema") != LEDGER_SCHEMA or not isinstance(value.get("entries"), list):
        raise BudgetError("invalid budget ledger")
    return value


def _charged(entry: dict[str, Any]) -> float:
    if entry.get("status") == "reserved":
        return float(entry["reserved_usd"])
    return float(entry.get("charged_usd", 0.0))


def ledger_totals(ledger: dict[str, Any]) -> dict[str, Any]:
    buckets = {key: 0.0 for key in ledger["bucket_caps_usd"]}
    for entry in ledger["entries"]:
        buckets.setdefault(entry["bucket"], 0.0)
        buckets[entry["bucket"]] += _charged(entry)
    return {"total_usd": sum(buckets.values()), "buckets_usd": buckets}


def reserve_cost(
    path: str | Path,
    *,
    bucket: str,
    amount_usd: float,
    job_id: str,
) -> str:
    ledger_path = Path(path)
    if amount_usd <= 0:
        raise BudgetError("reservation must be positive")
    with _file_lock(ledger_path):
        ledger = load_ledger(ledger_path)
        if ledger.get("halted"):
            raise BudgetError(f"budget ledger halted: {ledger.get('halt_reason')}")
        if bucket not in ledger["bucket_caps_usd"]:
            raise BudgetError(f"unknown budget bucket: {bucket}")
        totals = ledger_totals(ledger)
        if totals["total_usd"] + amount_usd > float(ledger["total_cap_usd"]) + 1e-12:
            raise BudgetError("$20 total budget would be exceeded before call")
        if (
            totals["buckets_usd"].get(bucket, 0.0) + amount_usd
            > float(ledger["bucket_caps_usd"][bucket]) + 1e-12
        ):
            raise BudgetError(f"{bucket} budget would be exceeded before call")
        reservation_id = uuid.uuid4().hex
        ledger["entries"].append(
            {
                "reservation_id": reservation_id,
                "job_id": job_id,
                "bucket": bucket,
                "reserved_usd": float(amount_usd),
                "charged_usd": None,
                "status": "reserved",
                "created_at": _now(),
            }
        )
        ledger["updated_at"] = _now()
        _atomic_json(ledger_path, ledger)
    return reservation_id


def settle_cost(
    path: str | Path,
    *,
    reservation_id: str,
    actual_cost_usd: float | None,
    usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ledger_path = Path(path)
    with _file_lock(ledger_path):
        ledger = load_ledger(ledger_path)
        matches = [
            entry
            for entry in ledger["entries"]
            if entry.get("reservation_id") == reservation_id
        ]
        if len(matches) != 1:
            raise BudgetError("unknown or duplicate reservation")
        entry = matches[0]
        if entry["status"] != "reserved":
            raise BudgetError("reservation was already settled")
        if actual_cost_usd is None:
            entry["charged_usd"] = float(entry["reserved_usd"])
            entry["status"] = "cost_unknown"
            ledger["halted"] = True
            ledger["halt_reason"] = "provider cost missing; reservation retained"
        else:
            if actual_cost_usd < 0:
                raise BudgetError("actual cost cannot be negative")
            entry["charged_usd"] = float(actual_cost_usd)
            entry["status"] = "settled"
        entry["usage"] = usage or {}
        entry["settled_at"] = _now()
        totals = ledger_totals(ledger)
        bucket = entry["bucket"]
        if (
            totals["total_usd"] > float(ledger["total_cap_usd"]) + 1e-12
            or totals["buckets_usd"][bucket]
            > float(ledger["bucket_caps_usd"][bucket]) + 1e-12
        ):
            ledger["halted"] = True
            ledger["halt_reason"] = "reported cost exceeded a configured cap"
        ledger["updated_at"] = _now()
        _atomic_json(ledger_path, ledger)
    return ledger
