from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable


def read_records(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    suffix = source.suffix.lower()
    if suffix == ".jsonl":
        return [
            json.loads(line)
            for line in source.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    if suffix == ".json":
        raw = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return [dict(item) for item in raw]
        if isinstance(raw, dict) and isinstance(raw.get("records"), list):
            return [dict(item) for item in raw["records"]]
        return [dict(raw)]
    if suffix == ".csv":
        with source.open(encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    raise ValueError(f"unsupported input suffix: {source.suffix}")


def write_jsonl(records: Iterable[dict[str, Any]], path: str | Path) -> int:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with target.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count
