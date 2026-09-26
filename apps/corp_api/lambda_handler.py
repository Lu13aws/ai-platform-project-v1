import asyncio

from aiplatform.loop import run_preserving_loop
from aiplatform.smoke import handle_smoke_test
from aiplatform.storage.corp_db import corp_engine
from aiplatform.storage.database import create_oneshot_engine
from apps.corp_api.main import app
from mangum import Mangum

_mangum = Mangum(app, lifespan="off")


async def _integrity_check() -> dict:
    """Read-only row counts of the corporate database (numbers only). Proves a restore brought the data back."""
    from aiplatform.storage.integrity import run_integrity_check
    from sqlalchemy import text

    engine = create_oneshot_engine(corp_engine.url)
    try:
        result = await run_integrity_check(engine)
        async with engine.connect() as conn:
            await conn.execute(text("SET TRANSACTION READ ONLY"))
            result["audit_logs"] = (await conn.execute(text("SELECT COUNT(*) FROM audit_logs"))).scalar_one()
        return result
    finally:
        await engine.dispose()


def handler(event, context):
    smoke = handle_smoke_test(event, "corp-api", lambda: create_oneshot_engine(corp_engine.url))
    if smoke is not None:
        return smoke
    if event.get("action") == "integrity_check":  # direct invoke only; API Gateway events carry no "action"
        return {"status": "ok", **run_preserving_loop(_integrity_check())}
    # Direct Lambda invocation for one-time admin tasks (not via API Gateway)
    if event.get("admin_action") == "setup_schema":
        import aiplatform.storage.corp_models  # noqa: F401 — registers AuditLog with Base
        from aiplatform.storage.corp_db import _CORP_DATABASE_URL
        from aiplatform.storage.models import Base
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        async def _setup():
            engine = create_async_engine(_CORP_DATABASE_URL)
            async with engine.begin() as conn:
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                await conn.run_sync(Base.metadata.create_all)
            await engine.dispose()

        asyncio.run(_setup())
        # Restore event loop after asyncio.run() closes it — needed for warm container reuse
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return {"status": "ok", "message": "Corp DB schema created"}

    return _mangum(event, context)
