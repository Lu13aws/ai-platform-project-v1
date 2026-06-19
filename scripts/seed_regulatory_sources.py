"""
Seed initial regulatory sources into the database.

Run once after the migration:
    uv run alembic upgrade head
    uv run python scripts/seed_regulatory_sources.py
"""

import asyncio
from datetime import UTC, datetime

from sqlalchemy import select

from aiplatform.storage.database import get_async_session
from aiplatform.storage.regulatory_models import RegulatorySource

SOURCES = [
    {
        "name": "EU AI Act (PDF)",
        "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=OJ:L_202401689",
        "source_type": "pdf",
        "domain": "AI",
    },
    {
        "name": "GDPR (PDF)",
        "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32016R0679",
        "source_type": "pdf",
        "domain": "Privacy",
    },
    {
        "name": "NIST Cybersecurity Framework 2.0",
        "url": "https://nvlpubs.nist.gov/nistpubs/CSWP/NIST.CSWP.29.pdf",
        "source_type": "pdf",
        "domain": "Cybersecurity",
    },
    {
        "name": "OWASP Top 10",
        "url": "https://owasp.org/www-project-top-ten/",
        "source_type": "html",
        "domain": "Cybersecurity",
    },
    {
        "name": "FINMA Risk Monitor",
        "url": "https://www.finma.ch/en/finma/publications/risk-monitor/",
        "source_type": "html",
        "domain": "Compliance",
    },
]


async def seed() -> None:
    async with get_async_session() as session:
        added = 0
        skipped = 0
        for s in SOURCES:
            existing = await session.scalar(
                select(RegulatorySource).where(RegulatorySource.url == s["url"])
            )
            if existing:
                print(f"  [skip] Already exists: {s['name']}")
                skipped += 1
                continue

            source = RegulatorySource(
                name=s["name"],
                url=s["url"],
                source_type=s["source_type"],
                domain=s["domain"],
                active=True,
                created_at=datetime.now(UTC),
            )
            session.add(source)
            print(f"  [add]  {s['name']} ({s['domain']})")
            added += 1

    print(f"\nDone — {added} added, {skipped} skipped.")


if __name__ == "__main__":
    asyncio.run(seed())
