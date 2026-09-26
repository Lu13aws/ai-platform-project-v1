"""
Seed initial competitor sources into the database.

Run once after the migration:
    uv run alembic upgrade head
    uv run python scripts/seed_competitor_sources.py

Idempotent: skips sources that already exist by URL.
"""

import asyncio
from datetime import UTC, datetime

from aiplatform.storage.competitor_models import CompetitorSource
from aiplatform.storage.database import get_async_session
from sqlalchemy import select

SOURCES = [
    # ── OpenAI ────────────────────────────────────────────────────────────────
    {
        "company_name": "OpenAI",
        "name": "OpenAI Blog",
        "url": "https://openai.com/blog/rss.xml",
        "source_type": "blog",
    },
    {
        "company_name": "OpenAI",
        "name": "OpenAI API Pricing",
        "url": "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json",
        "source_type": "pricing",
    },
    {
        "company_name": "OpenAI",
        "name": "HN: OpenAI",
        "url": "hn://OpenAI",
        "source_type": "community",
    },

    # ── Anthropic ─────────────────────────────────────────────────────────────
    {
        "company_name": "Anthropic",
        "name": "Anthropic News",
        "url": "https://www.anthropic.com/news",
        "source_type": "blog",
    },
    {
        "company_name": "Anthropic",
        "name": "Anthropic Pricing",
        "url": "https://www.anthropic.com/pricing",
        "source_type": "pricing",
    },
    {
        "company_name": "Anthropic",
        "name": "HN: Anthropic",
        "url": "hn://Anthropic",
        "source_type": "community",
    },

    # ── Microsoft ─────────────────────────────────────────────────────────────
    {
        "company_name": "Microsoft",
        "name": "Microsoft AI Blog",
        "url": "https://azure.microsoft.com/en-us/blog/feed/",
        "source_type": "blog",
    },
    {
        "company_name": "Microsoft",
        "name": "Azure AI Pricing",
        "url": "https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/",
        "source_type": "pricing",
    },
    {
        "company_name": "Microsoft",
        "name": "MSFT Stock",
        "url": "yahoo://MSFT",
        "source_type": "financial",
    },
    {
        "company_name": "Microsoft",
        "name": "HN: Microsoft AI",
        "url": "hn://Microsoft Copilot",
        "source_type": "community",
    },

    # ── AWS ───────────────────────────────────────────────────────────────────
    {
        "company_name": "AWS",
        "name": "AWS ML Blog",
        "url": "https://aws.amazon.com/blogs/machine-learning/feed/",
        "source_type": "blog",
    },
    {
        "company_name": "AWS",
        "name": "Amazon Bedrock Pricing",
        "url": "https://aws.amazon.com/bedrock/pricing/",
        "source_type": "pricing",
    },
    {
        "company_name": "AWS",
        "name": "AMZN Stock",
        "url": "yahoo://AMZN",
        "source_type": "financial",
    },
    {
        "company_name": "AWS",
        "name": "HN: AWS Bedrock",
        "url": "hn://Amazon Bedrock",
        "source_type": "community",
    },

    # ── Google ────────────────────────────────────────────────────────────────
    {
        "company_name": "Google",
        "name": "Google Cloud AI Blog",
        "url": "https://cloud.google.com/blog/products/ai-machine-learning/rss/",
        "source_type": "blog",
    },
    {
        "company_name": "Google",
        "name": "Vertex AI Pricing",
        "url": "https://cloud.google.com/vertex-ai/generative-ai/pricing",
        "source_type": "pricing",
    },
    {
        "company_name": "Google",
        "name": "GOOGL Stock",
        "url": "yahoo://GOOGL",
        "source_type": "financial",
    },
    {
        "company_name": "Google",
        "name": "HN: Google Gemini",
        "url": "hn://Google Gemini",
        "source_type": "community",
    },

    # ── Mistral AI ────────────────────────────────────────────────────────────
    {
        "company_name": "Mistral AI",
        "name": "Mistral AI News",
        "url": "https://mistral.ai/news",
        "source_type": "blog",
    },
    {
        "company_name": "Mistral AI",
        "name": "Mistral AI Pricing",
        "url": "https://mistral.ai/technology",
        "source_type": "pricing",
    },
    {
        "company_name": "Mistral AI",
        "name": "HN: Mistral AI",
        "url": "hn://Mistral AI",
        "source_type": "community",
    },
]


async def seed() -> None:
    async with get_async_session() as session:
        added = 0
        skipped = 0
        for s in SOURCES:
            existing = await session.scalar(
                select(CompetitorSource).where(CompetitorSource.url == s["url"])
            )
            if existing:
                print(f"  [skip] {s['name']}")
                skipped += 1
                continue

            source = CompetitorSource(
                company_name=s["company_name"],
                name=s["name"],
                url=s["url"],
                source_type=s["source_type"],
                active=True,
                created_at=datetime.now(UTC),
            )
            session.add(source)
            print(f"  [add]  {s['company_name']} / {s['name']} ({s['source_type']})")
            added += 1

    print(f"\nDone - {added} added, {skipped} skipped.")


if __name__ == "__main__":
    asyncio.run(seed())
