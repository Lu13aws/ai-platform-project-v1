"""
Phase 6 — Create tables in ai-platform-db-corp.

Runs via a temporary bastion Lambda (or locally via SSH tunnel) since the DB
has no public endpoint.

Creates:
  - pgvector extension
  - documents, chunks, embeddings (from models.Base)
  - audit_logs (from corp_models)

Usage (requires CORP_DATABASE_URL env var pointing to the corp DB):
    CORP_DATABASE_URL="postgresql+asyncpg://..." uv run python scripts/setup_corp_schema.py

For Lambda deployment: run this once after deploy via the setup endpoint.
"""

import asyncio
import os
import sys


async def main() -> None:
    corp_url = os.environ.get("CORP_DATABASE_URL")
    if not corp_url:
        print("ERROR: CORP_DATABASE_URL not set")
        sys.exit(1)

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    # Import models to register them with Base.metadata
    import aiplatform.storage.corp_models  # noqa: F401
    from aiplatform.storage.models import Base

    engine = create_async_engine(corp_url, echo=True)

    async with engine.begin() as conn:
        print("[schema] creating pgvector extension...")
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

        print("[schema] creating tables...")
        await conn.run_sync(Base.metadata.create_all)

    await engine.dispose()
    print("[schema] done — corp DB schema ready")


if __name__ == "__main__":
    asyncio.run(main())
