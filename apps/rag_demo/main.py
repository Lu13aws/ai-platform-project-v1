from aiplatform.settings import settings
from aiplatform.storage.models import Base
from apps.knowledge_platform.api.routes import router as kp_router
from apps.rag_demo.api.radar_routes import router as radar_router
from apps.rag_demo.api.routes import router
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine as _create_sync_engine

# Import all model modules so their tables are registered with Base.metadata.
import aiplatform.storage.content_models  # noqa: F401

# Create any missing tables on Lambda cold start using a sync psycopg2 engine.
# Uses ALEMBIC_DATABASE_URL (postgresql://... ?sslmode=require) which is the
# psycopg2-compatible version of DATABASE_URL set in the Lambda env vars.
# Safe to run repeatedly — uses CREATE TABLE IF NOT EXISTS semantics.
_sync_engine = _create_sync_engine(settings.alembic_database_url)
Base.metadata.create_all(_sync_engine)
_sync_engine.dispose()

app = FastAPI(
    title=settings.rag_demo_title,
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

_PRODUCTION_ORIGINS = [
    "https://bridging-data.com",
    "https://www.bridging-data.com",
    "https://platform.bridging-data.com",
    "http://localhost:3000",
    "http://localhost:3001",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.is_development else _PRODUCTION_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(router, prefix="/api/v1")
app.include_router(radar_router, prefix="/api/v1")
app.include_router(kp_router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "app": settings.rag_demo_title}
