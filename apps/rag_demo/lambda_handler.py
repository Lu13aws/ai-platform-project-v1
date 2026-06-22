import asyncio

from mangum import Mangum

from apps.rag_demo.main import app

_mangum = Mangum(app, lifespan="off")


async def _run_migrations() -> list[str]:
    """Apply DDL changes directly — alembic.ini not available in Lambda image."""
    from sqlalchemy import text
    from aiplatform.storage.database import engine

    applied = []
    async with engine.begin() as conn:
        # Migration f2a9c4e8b1d3: create linkedin_posts table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS linkedin_posts (
                id UUID PRIMARY KEY,
                domain VARCHAR(20) NOT NULL,
                angle VARCHAR(20) NOT NULL,
                company VARCHAR(100) NOT NULL,
                content TEXT NOT NULL,
                linkedin_post_id VARCHAR(200),
                linkedin_post_url VARCHAR(500),
                posted_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL
            )
        """))
        applied.append("f2a9c4e8b1d3: linkedin_posts table ensured")

        # Migration b3e7f2a1c9d5: add status column
        await conn.execute(text("""
            ALTER TABLE linkedin_posts
            ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'draft'
        """))
        applied.append("b3e7f2a1c9d5: status column ensured")

        # Ensure indexes
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_linkedin_posts_posted_at ON linkedin_posts (posted_at)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_linkedin_posts_domain ON linkedin_posts (domain)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_linkedin_posts_status ON linkedin_posts (status)
        """))

    return applied


def handler(event, context):
    if event.get("action") == "run_migrations":
        applied = asyncio.run(_run_migrations())
        return {"status": "ok", "applied": applied}
    return _mangum(event, context)
