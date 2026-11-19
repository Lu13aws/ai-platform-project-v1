"""
Technology Radar sources — single list used by scripts/seed_radar_sources.py and by the radar
Lambda's {"action": "sync_sources"} (the database sits in a private VPC, so the Lambda is the only
way to add sources in production).

Two kinds of sources:
  vendor       : the vendors' own news (AWS, Anthropic, Databricks) — what they announce
  independent  : practitioner and tech press — how others see it. Added 2026-11-19 so that Phase 7
                 can compare vendor claims (Competitor Radar) with outside views (this radar);
                 before that, both radars read the same Anthropic news page.

sync_sources() only inserts sources that are missing (matched by URL). It never edits, deactivates
or deletes an existing source.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aiplatform.storage.radar_models import RadarSource

SOURCES = [
    # vendor
    {"name": "AWS", "url": "https://aws.amazon.com/new/",
     "feed_url": "https://aws.amazon.com/blogs/aws/feed/", "source_type": "rss"},
    {"name": "Anthropic", "url": "https://www.anthropic.com/news",
     "feed_url": None, "source_type": "html"},
    {"name": "Databricks", "url": "https://www.databricks.com/blog",
     "feed_url": "https://www.databricks.com/feed", "source_type": "rss"},
    # independent (feeds checked 2026-11-19: 20 items each, about half name a tracked competitor)
    {"name": "The New Stack", "url": "https://thenewstack.io/",
     "feed_url": "https://thenewstack.io/feed/", "source_type": "rss"},
    {"name": "The Register AI/ML", "url": "https://www.theregister.com/software/ai_ml/",
     "feed_url": "https://www.theregister.com/software/ai_ml/headlines.atom", "source_type": "rss"},
    {"name": "Simon Willison", "url": "https://simonwillison.net/",
     "feed_url": "https://simonwillison.net/atom/everything/", "source_type": "rss"},
    {"name": "Ars Technica AI", "url": "https://arstechnica.com/ai/",
     "feed_url": "https://arstechnica.com/ai/feed/", "source_type": "rss"},
]


async def sync_sources(session: AsyncSession, dry_run: bool = True) -> dict:
    """Insert the sources from SOURCES that are not in radar_sources yet."""
    existing_urls = set((await session.scalars(select(RadarSource.url))).all())
    missing = [s for s in SOURCES if s["url"] not in existing_urls]

    if not dry_run:
        now = datetime.now(UTC)
        for s in missing:
            session.add(RadarSource(**s, active=True, created_at=now))

    return {
        "dry_run": dry_run,
        "existing": len(SOURCES) - len(missing),
        "added" if not dry_run else "would_add": [s["name"] for s in missing],
    }
