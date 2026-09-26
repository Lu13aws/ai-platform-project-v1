from aiplatform.quota import register_quota_handler
from apps.knowledge_platform.api.routes import router
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="AI Knowledge Platform",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)
register_quota_handler(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_methods=["GET", "POST", "DELETE", "PATCH"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "app": "AI Knowledge Platform"}
