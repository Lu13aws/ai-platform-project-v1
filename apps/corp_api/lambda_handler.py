import asyncio

from apps.corp_api.main import app
from mangum import Mangum

_mangum = Mangum(app, lifespan="off")


def handler(event, context):
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
