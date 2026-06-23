from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.corp_api.api.routes import router

app = FastAPI(
    title="AI Knowledge Platform — Corporate",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "https://bridging-data.com",
        "https://www.bridging-data.com",
        "https://platform.bridging-data.com",
    ],
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(router, prefix="/api/v1")
