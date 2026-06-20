"""验证审计 JSONL 文件的哈希链 + 字段完整性。

用法：
    PYTHONPATH=src python scripts/verify_audit.py --path logs/audit/audit.jsonl
    PYTHONPATH=src python scripts/verify_audit.py --path logs/audit/audit.jsonl --anchor logs/audit/anchor.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from xa_guard.audit.archive import verify_audit_jsonl, verify_audit_signatures
from xa_guard.audit.tsa import verify_file_anchor

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


def _reject_nonfinite(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is not allowed: {value}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default="logs/audit/audit.jsonl")
    parser.add_argument("--algo", choices=["sha256", "sm3"], default="sha256")
    parser.add_argument("--anchor", help="optional local file TSA anchor manifest to verify")
    parser.add_argument("--verify-anchor-index", action="store_true", help="also require the anchor index entry")
    parser.add_argument(
        "--require-signature",
        choices=["sm2", "hmac-demo"],
        help="require and verify every record signature in the selected mode",
    )
    parser.add_argument("--signature-key", default="", help="SM2 or demo HMAC key file")
    args = parser.parse_args()

    p = Path(args.path)
    if not p.exists():
        print(f"file not found: {p}", file=sys.stderr)
        return 2

    ok = 0
    parse_errors = 0
    missing_fields = 0
    with open(p, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line, parse_constant=_reject_nonfinite)
            except Exception as exc:
                print(f"line {i}: JSON parse error: {exc}")
                parse_errors += 1
                continue

            # 字段完整性
            missing = [k for k in REQUIRED_FIELDS if k not in rec]
            if missing:
                print(f"line {i}: missing fields: {missing}")
                missing_fields += 1

            ok += 1

    chain = verify_audit_jsonl(p, algo=args.algo)
    if not chain["ok"]:
        print(
            "hash-chain verification failed: "
            f"{chain['error_count']} error record(s), first at line {chain['first_error_line']}"
        )

    anchor_errors = 0
    if args.anchor:
        try:
            anchor = verify_file_anchor(p, args.anchor, algo=args.algo, verify_index=args.verify_anchor_index)
        except Exception as exc:
            anchor_errors = 1
            print(f"anchor verification failed: {exc}")
        else:
            print(
                "anchor verified: "
                f"{anchor.anchor_path} -> {anchor.manifest['anchored_record_hash'][:16]}"
            )

    signature_errors = 0
    if args.require_signature:
        try:
            signatures = verify_audit_signatures(
                p,
                mode=args.require_signature,
                key_path=args.signature_key,
            )
        except Exception as exc:
            signature_errors = 1
            print(f"signature verification setup failed: {exc}")
        else:
            signature_errors = signatures["error_count"]
            if not signatures["ok"] and signature_errors == 0:
                signature_errors = 1
            print(
                "signatures verified: "
                f"mode={signatures['mode']} records={signatures['record_count']} "
                f"errors={signatures['error_count']} key_id={signatures['expected_key_id']}"
            )

    print(
        f"\nverified {ok} records, {chain['error_count']} chain/hash errors, "
        f"{parse_errors} JSON parse errors, {missing_fields} missing-field records, "
        f"{anchor_errors} anchor errors, {signature_errors} signature errors"
    )
    return (
        0
        if chain["ok"]
        and parse_errors == 0
        and missing_fields == 0
        and anchor_errors == 0
        and signature_errors == 0
        else 1
    )


if __name__ == "__main__":
    sys.exit(main())
