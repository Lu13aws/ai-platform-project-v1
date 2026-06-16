from aiplatform.settings import settings
from apps.rag_demo.api.routes import router
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title=settings.rag_demo_title,
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

_PRODUCTION_ORIGINS = ["https://bridging-data.com"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.is_development else _PRODUCTION_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "app": settings.rag_demo_title}
