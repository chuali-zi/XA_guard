"""Idempotent, advisory-lock protected migration entry point."""

from __future__ import annotations

import asyncio

from xa_guard.control.runtime import build_runtime


async def migrate() -> None:
    runtime = build_runtime()
    await runtime.store.connect()
    try:
        await runtime.store.migrate()
    finally:
        await runtime.store.close()


if __name__ == "__main__":
    asyncio.run(migrate())

