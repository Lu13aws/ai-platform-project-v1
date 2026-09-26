
from aiplatform.loop import run_preserving_loop
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
    from aiplatform.storage.database import create_oneshot_engine
    from aiplatform.storage.integrity import run_integrity_check

    engine = create_oneshot_engine()
    try:
        return await run_integrity_check(engine)
    finally:
        await engine.dispose()


async def _list_documents(app_name: str) -> list[dict]:
    """Read-only document metadata (no content) of one namespace."""
    from aiplatform.storage.database import create_oneshot_engine
    from aiplatform.storage.integrity import list_document_metadata

    engine = create_oneshot_engine()
    try:
        return await list_document_metadata(engine, app_name)
    finally:
        await engine.dispose()


async def _delete_namespace(app_name, expected_documents, confirm, dry_run: bool) -> dict:
    """Guarded, transactional namespace deletion (dry run unless dry_run is explicitly False)."""
    from aiplatform.storage.database import create_oneshot_engine
    from aiplatform.storage.namespace_delete import delete_namespace

    engine = create_oneshot_engine()
    try:
        return await delete_namespace(engine, app_name, expected_documents, confirm, dry_run)
    finally:
        await engine.dispose()


def handler(event, context):
    smoke = handle_smoke_test(event, "rag-demo")
    if smoke is not None:
        return smoke
    # Direct-invoke actions: API Gateway events never carry a top-level "action" key,
    # so these are reachable only with lambda:InvokeFunction, not over HTTP.
    if event.get("action") == "run_migrations":
        applied = run_preserving_loop(_run_migrations())
        return {"status": "ok", "applied": applied}
    if event.get("action") == "integrity_check":
        return {"status": "ok", **run_preserving_loop(_integrity_check())}
    if event.get("action") == "list_documents":
        app_name = event.get("app_name")
        if not isinstance(app_name, str) or not app_name:
            return {"status": "error", "error": "list_documents needs a non-empty app_name"}
        documents = run_preserving_loop(_list_documents(app_name))
        return {"status": "ok", "app_name": app_name, "count": len(documents), "documents": documents}
    if event.get("action") == "delete_namespace":
        from aiplatform.storage.namespace_delete import NamespaceDeleteRefused

        try:
            result = run_preserving_loop(
                _delete_namespace(
                    event.get("app_name"),
                    event.get("expected_documents"),
                    event.get("confirm"),
                    event.get("dry_run") is not False,  # anything but an explicit false stays a dry run
                )
            )
        except NamespaceDeleteRefused as exc:
            return {"status": "refused", "error": str(exc)}
        return {"status": "ok", **result}
    return _mangum(event, context)
