"""Direct-invoke smoke test shared by every Lambda handler.

{"action": "smoke_test"} proves a healthy cold start without running a pipeline: the handler module
imported, secrets were loaded, settings validated and the database answers SELECT 1. API Gateway and
EventBridge events carry no top-level "action" key, so this is reachable only with
lambda:InvokeFunction. It never reads or writes application data.
"""

import asyncio
from collections.abc import Callable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


def _public_engine() -> AsyncEngine:
    from aiplatform.storage.database import engine

    return engine


async def _ping(engine: AsyncEngine) -> None:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    finally:
        await engine.dispose()  # asyncio.run() gives every call its own event loop


def handle_smoke_test(
    event, function_name: str, get_engine: Callable[[], AsyncEngine] = _public_engine
) -> dict | None:
    """Result for {"action": "smoke_test"}; None for every other event so the handler carries on."""
    if not isinstance(event, dict) or event.get("action") != "smoke_test":
        return None

    from aiplatform.settings import settings

    result = {"function": function_name, "app_env": settings.app_env}
    try:
        asyncio.run(_ping(get_engine()))
        outcome = {"status": "ok", **result, "database": "ok"}
    except Exception as exc:
        outcome = {"status": "error", **result, "database": f"{type(exc).__name__}: {str(exc)[:200]}"}
    # Mangum-based handlers need a current event loop again after asyncio.run() closed it.
    asyncio.set_event_loop(asyncio.new_event_loop())
    return outcome
