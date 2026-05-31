"""Archive the current audit JSONL without repairing or rewriting it.

Usage:
    python scripts/archive_audit.py --path logs/audit/audit.jsonl --reason known-corrupt-sample
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from xa_guard.audit.archive import archive_audit_log


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default="logs/audit/audit.jsonl")
    parser.add_argument("--archive-dir", default=None)
    parser.add_argument("--reason", default="manual-archive")
    parser.add_argument("--hash-algo", default="sha256")
    parser.add_argument(
        "--create-empty",
        action="store_true",
        help="create an empty source file after archiving; default leaves it absent until the next append",
    )
    args = parser.parse_args()

    try:
        result = archive_audit_log(
            Path(args.path),
            archive_dir=Path(args.archive_dir) if args.archive_dir else None,
            reason=args.reason,
            algo=args.hash_algo,
            create_empty=args.create_empty,
        )
    except Exception as exc:
        print(f"archive failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result.manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
