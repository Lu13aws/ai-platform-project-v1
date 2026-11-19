#!/usr/bin/env python3
"""
Seed the radar_sources table with the Technology Radar sources (aiplatform/agents/radar_sources.py).

For a local database. The production database is in a private VPC; there, invoke the radar Lambda
with {"action": "sync_sources"} (dry run) and then {"action": "sync_sources", "dry_run": false}.

Usage:
    uv run python scripts/seed_radar_sources.py

Re-running is safe: existing sources (matched by URL) are skipped.
"""

import asyncio

from aiplatform.agents.radar_sources import sync_sources
from aiplatform.storage.database import get_async_session


async def seed() -> None:
    async with get_async_session() as session:
        result = await sync_sources(session, dry_run=False)
    print(f"  Done: {len(result['added'])} inserted {result['added']}, {result['existing']} skipped")


if __name__ == "__main__":
    asyncio.run(seed())
