#!/usr/bin/env python3
"""Quick DB check — prints row counts for all radar tables."""

import asyncio

from aiplatform.storage.database import get_async_session
from aiplatform.storage.radar_models import (
    RadarEntry,
    RadarReport,
    RadarSignal,
    RadarSource,
    RawArticle,
)
from sqlalchemy import func, select


async def main() -> None:
    async with get_async_session() as session:
        for model in [RadarSource, RawArticle, RadarSignal, RadarEntry, RadarReport]:
            count = await session.scalar(select(func.count()).select_from(model))
            print(f"  {model.__tablename__}: {count} rows")

        unprocessed = await session.scalar(
            select(func.count()).select_from(RawArticle).where(RawArticle.processed_at.is_(None))
        )
        print(f"\n  raw_articles with processed_at = NULL: {unprocessed}")


if __name__ == "__main__":
    asyncio.run(main())
