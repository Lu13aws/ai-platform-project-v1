"""
Async SQLAlchemy engine and session factory.

Usage:
    from aiplatform.storage.database import get_async_session

    async with get_async_session() as session:
        result = await session.execute(select(Document))
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from aiplatform.settings import settings

engine = create_async_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    echo=settings.db_echo,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


def create_oneshot_engine(url=None) -> AsyncEngine:
    """Unpooled engine for direct-invoke actions (smoke test, integrity check, ...).

    asyncio.run() gives each call its own event loop, and a pooled connection created by an earlier
    HTTP request lives in another loop ("attached to a different loop"). One-shot engines never
    touch the shared pool. Dispose the engine when done.
    """
    return create_async_engine(url or settings.database_url, poolclass=NullPool)


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a session per request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
