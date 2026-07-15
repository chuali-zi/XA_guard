"""Idempotent, advisory-lock protected migration entry point."""

from __future__ import annotations

import asyncio

from xa_guard.control.runtime import build_migration_store


async def migrate() -> None:
    store = build_migration_store()
    await store.connect()
    try:
        await store.migrate()
    finally:
        await store.close()


if __name__ == "__main__":
    asyncio.run(migrate())
