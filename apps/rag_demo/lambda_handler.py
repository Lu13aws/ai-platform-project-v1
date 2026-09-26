import asyncio

from aiplatform.smoke import handle_smoke_test
from apps.rag_demo.main import app
from mangum import Mangum

_mangum = Mangum(app, lifespan="off")


async def _run_migrations() -> list[str]:
    """Apply DDL changes directly — alembic.ini not available in Lambda image."""
    from aiplatform.storage.database import engine
    from sqlalchemy import text

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


async def _integrity_check() -> dict:
    """Read-only counts (chunks without embedding, ...). Numbers only, no content."""
    from aiplatform.storage.database import engine
    from aiplatform.storage.integrity import run_integrity_check

    try:
        return await run_integrity_check(engine)
    finally:
        await engine.dispose()  # asyncio.run() gives every call its own event loop


def _run(coro):
    """asyncio.run() closes the loop; Mangum needs a current one again when the same warm
    container serves the next HTTP request, otherwise every request returns 500."""
    try:
        return asyncio.run(coro)
    finally:
        asyncio.set_event_loop(asyncio.new_event_loop())


def handler(event, context):
    smoke = handle_smoke_test(event, "rag-demo")
    if smoke is not None:
        return smoke
    # Direct-invoke actions: API Gateway events never carry a top-level "action" key,
    # so these are reachable only with lambda:InvokeFunction, not over HTTP.
    if event.get("action") == "run_migrations":
        applied = _run(_run_migrations())
        return {"status": "ok", "applied": applied}
    if event.get("action") == "integrity_check":
        return {"status": "ok", **_run(_integrity_check())}
    return _mangum(event, context)
