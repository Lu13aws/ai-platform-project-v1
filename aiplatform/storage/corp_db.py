"""
Separate async engine + session factory for the Phase 6 Corporate DB.

Reads CORP_DATABASE_URL from environment — must point to ai-platform-db-corp.
Intentionally separate from the public shared database.py.

Usage:
    from aiplatform.storage.corp_db import get_corp_session

    async with get_corp_session() as session:
        ...
"""

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_CORP_DATABASE_URL = os.environ.get(
    "CORP_DATABASE_URL",
    "postgresql+asyncpg://aiplatform:aiplatform@localhost:5432/aiplatform_corp",
)

corp_engine = create_async_engine(
    _CORP_DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    echo=False,
)

_CorpSessionLocal = async_sessionmaker(
    bind=corp_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@asynccontextmanager
async def get_corp_session() -> AsyncGenerator[AsyncSession, None]:
    async with _CorpSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_corp_session_dep() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a corp session per request."""
    async with _CorpSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
