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

from aiplatform.secrets import load_json_secret_into_env

# Corp-only secret, separate from the shared ai-platform/app-secrets used by
# every other Lambda — see scripts/deploy_corp_api.py and the dormant
# CorpSecretsAccess IAM policy it grants (now actually consumed via this
# secret name matching the policy's arn:...:secret:ai-platform/corp-*
# resource pattern).
load_json_secret_into_env("ai-platform/corp-app-secrets")

_DEFAULT_CORP_DATABASE_URL = "postgresql+asyncpg://aiplatform:aiplatform@localhost:5432/aiplatform_corp"

_CORP_DATABASE_URL = os.environ.get("CORP_DATABASE_URL", _DEFAULT_CORP_DATABASE_URL)

# Reads APP_ENV directly instead of importing aiplatform.settings.settings:
# this module intentionally bypasses settings.py entirely (see module
# docstring), and importing the shared Settings object here would force its
# full construction/validation (including the unrelated public DATABASE_URL
# field) just to read one flag — a real failure mode, not hypothetical: it
# broke corp_api's cold start in production before this fix.
if os.environ.get("APP_ENV", "development") == "production" and (
    _CORP_DATABASE_URL == _DEFAULT_CORP_DATABASE_URL
):
    raise RuntimeError(
        "CORP_DATABASE_URL is still the local-dev default (aiplatform:aiplatform) "
        "in production - set a real CORP_DATABASE_URL."
    )

corp_engine = create_async_engine(
    _CORP_DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,  # the instance can be deleted and restored from a snapshot (corp_db_down/up)
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
