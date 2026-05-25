"""验证审计 JSONL 文件的哈希链 + 14 字段完整性。

用法：
    python scripts/verify_audit.py --path logs/audit/audit.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REQUIRED_FIELDS = [
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
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default="logs/audit/audit.jsonl")
    args = parser.parse_args()

    p = Path(args.path)
    if not p.exists():
        print(f"file not found: {p}", file=sys.stderr)
        return 2

    prev = ""
    ok = 0
    failed = 0
    missing_fields = 0
    with open(p, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception as exc:
                print(f"line {i}: JSON parse error: {exc}")
                failed += 1
                continue

            # 字段完整性
            missing = [k for k in REQUIRED_FIELDS if k not in rec]
            if missing:
                print(f"line {i}: missing fields: {missing}")
                missing_fields += 1

            # 哈希链
            actual_prev = rec.get("gen_ai.evidence.hash_prev", "")
            if i > 1 and actual_prev != prev:
                print(f"line {i}: hash_prev mismatch (expected {prev[:16]}, got {actual_prev[:16]})")
                failed += 1
            prev = rec.get("record_hash", "")
            ok += 1

    print(f"\nverified {ok} records, {failed} chain errors, {missing_fields} missing-field records")
    return 0 if failed == 0 and missing_fields == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
