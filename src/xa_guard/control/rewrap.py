"""Online recovery-material DEK rewrap CLI."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from xa_guard.control.crypto import CryptoError
from xa_guard.control.key_provider import KeyProviderError
from xa_guard.control.runtime import build_keyed_store
from xa_guard.control.store import StoreError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rewrap XA-Guard effect DEKs with the active KEK"
    )
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument(
        "--max-records",
        type=int,
        default=0,
        help="maximum records to update; 0 processes all remaining records",
    )
    return parser


async def rewrap(*, batch_size: int = 100, max_records: int = 0) -> dict[str, object]:
    if batch_size < 1 or batch_size > 10_000 or max_records < 0:
        raise ValueError("batch-size must be 1..10000 and max-records must be non-negative")
    store, provider = build_keyed_store()
    total = 0
    try:
        await provider.start()
        if not await provider.ready():
            raise KeyProviderError("key provider is not ready")
        await store.connect()
        while max_records == 0 or total < max_records:
            limit = batch_size
            if max_records:
                limit = min(limit, max_records - total)
            changed = await store.rewrap_batch(limit)
            total += changed
            if changed == 0:
                break
        return {"rewrapped": total, "active_key_id": provider.active_key_id}
    finally:
        await store.close()
        await provider.close()


def main() -> None:
    args = _parser().parse_args()
    try:
        result = asyncio.run(
            rewrap(batch_size=args.batch_size, max_records=args.max_records)
        )
    except (CryptoError, KeyProviderError, StoreError, ValueError):
        print("rewrap failed: storage or key provider is unavailable", file=sys.stderr)
        raise SystemExit(1) from None
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
