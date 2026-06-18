"""Create a local file TSA anchor for an audit JSONL file.

Usage:
    PYTHONPATH=src python scripts/anchor_audit.py --path logs/audit/audit.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys

from xa_guard.audit.tsa import create_file_anchor


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default="logs/audit/audit.jsonl")
    parser.add_argument("--anchor-path", help="where to write the anchor manifest")
    parser.add_argument("--index-path", help="where to append the anchor index JSONL")
    parser.add_argument("--no-index", action="store_true", help="write only the anchor manifest")
    parser.add_argument("--algo", choices=["sha256", "sm3"], default="sha256")
    args = parser.parse_args()

    try:
        result = create_file_anchor(
            args.path,
            anchor_path=args.anchor_path,
            index_path=args.index_path,
            algo=args.algo,
            update_index=not args.no_index,
        )
    except Exception as exc:
        print(f"failed to create audit anchor: {exc}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "audit_path": str(result.audit_path),
                "anchor_path": str(result.anchor_path),
                "record_count": result.manifest["record_count"],
                "anchored_record_hash": result.manifest["anchored_record_hash"],
                "anchor_sequence": result.manifest["anchor_sequence"],
                "previous_anchor_hash": result.manifest["previous_anchor_hash"],
                "anchor_index_path": result.manifest["anchor_index_path"],
                "tsa_token": result.manifest["tsa_token"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
