#!/usr/bin/env python3
"""
Seed the radar_sources table with the 3 initial Technology Radar sources.

Usage:
    uv run python scripts/seed_radar_sources.py

Re-running is safe: existing sources (matched by URL) are skipped.
"""

import asyncio
from datetime import UTC, datetime

from aiplatform.storage.database import get_async_session
from aiplatform.storage.radar_models import RadarSource
from sqlalchemy import select

SOURCES = [
    {
        "name": "AWS",
        "url": "https://aws.amazon.com/new/",
        "feed_url": "https://aws.amazon.com/blogs/aws/feed/",
        "source_type": "rss",
    },
    {
        "name": "Anthropic",
        "url": "https://www.anthropic.com/news",
        "feed_url": None,
        "source_type": "html",
    },
    {
        "name": "Databricks",
        "url": "https://www.databricks.com/blog",
        "feed_url": "https://www.databricks.com/feed",
        "source_type": "rss",
    },
]


async def seed() -> None:
    async with get_async_session() as session:
        inserted = 0
        skipped = 0

        for source_data in SOURCES:
            existing = await session.scalar(
                select(RadarSource).where(RadarSource.url == source_data["url"])
            )
            if existing:
                print(f"  [skip] {source_data['name']} already exists")
                skipped += 1
                continue

            source = RadarSource(
                name=source_data["name"],
                url=source_data["url"],
                feed_url=source_data["feed_url"],
                source_type=source_data["source_type"],
                active=True,
                created_at=datetime.now(UTC),
            )
            session.add(source)
            print(f"  [ok]   {source_data['name']} ({source_data['source_type']}) — {source_data['url']}")
            inserted += 1

    print(f"\n  Done: {inserted} inserted, {skipped} skipped")


if __name__ == "__main__":
    asyncio.run(seed())
