"""
Private Knowledge Hub — local FastAPI application.

Runs on http://localhost:8001 (separate port from the RAG demo).
All data is scoped to app_name="private_hub" and never exposed publicly.

Start:
    make run-private-hub
    # or: uv run uvicorn apps.private_hub.main:app --reload --port 8001
"""

from pathlib import Path
from uuid import UUID

from aiplatform.settings import settings
from aiplatform.storage.database import get_async_session
from aiplatform.storage.models import Document
from apps.private_hub.ingester import APP_NAME, FolderIngester, IngestResult
from apps.rag_demo.api.schemas import QueryRequest, QueryResponse
from apps.rag_demo.services.query_service import QueryService
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import func, select

_PRIVATE_HUB_SYSTEM_PROMPT = """\
You are a personal knowledge assistant with access to the user's own project documents,
notes, and learning materials. Answer questions using only the provided context.
Cite sources with [1], [2], etc. labels.
If the context does not contain enough information, say so — do not guess or invent details.
Keep answers concise and practical.\
"""

_STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title="Private Knowledge Hub",
    description="Personal document retrieval — local only, never exposed publicly.",
    version="1.0.0",
    docs_url="/docs",
)


# ── Schemas ────────────────────────────────────────────────────────────────────

class IngestFolderRequest(BaseModel):
    paths: list[str]


class IngestFolderResponse(BaseModel):
    ingested: int
    skipped: int
    unsupported: int
    errors: list[str]


class SourceItem(BaseModel):
    document_id: str
    title: str | None
    source_uri: str
    mime_type: str | None


class SourcesResponse(BaseModel):
    total: int
    documents: list[SourceItem]


class StatsResponse(BaseModel):
    document_count: int
    llm_provider: str
    llm_model: str


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "app": "private_hub"}


# ── Ingest ─────────────────────────────────────────────────────────────────────

@app.post("/ingest", response_model=IngestFolderResponse)
async def ingest_folders(request: IngestFolderRequest) -> IngestFolderResponse:
    paths = [Path(p) for p in request.paths]
    async with get_async_session() as session:
        ingester = FolderIngester(session)
        result: IngestResult = await ingester.run(paths)
    return IngestFolderResponse(
        ingested=result.ingested,
        skipped=result.skipped,
        unsupported=result.unsupported,
        errors=result.errors,
    )


# ── Query ──────────────────────────────────────────────────────────────────────

@app.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest) -> QueryResponse:
    async with get_async_session() as session:
        service = QueryService(
            session,
            app_name=APP_NAME,
            system_prompt=_PRIVATE_HUB_SYSTEM_PROMPT,
            similarity_threshold=0.25,
        )
        return await service.query(request)


# ── Sources ────────────────────────────────────────────────────────────────────

@app.get("/sources", response_model=SourcesResponse)
async def list_sources() -> SourcesResponse:
    async with get_async_session() as session:
        rows = (await session.scalars(
            select(Document)
            .where(Document.app_name == APP_NAME)
            .order_by(Document.title)
        )).all()
    return SourcesResponse(
        total=len(rows),
        documents=[
            SourceItem(
                document_id=str(d.id),
                title=d.title,
                source_uri=d.source_uri,
                mime_type=d.mime_type,
            )
            for d in rows
        ],
    )


# ── Delete source ──────────────────────────────────────────────────────────────

@app.delete("/sources/{document_id}")
async def delete_source(document_id: str) -> dict:
    async with get_async_session() as session:
        doc = await session.get(Document, UUID(document_id))
        if doc is None or doc.app_name != APP_NAME:
            raise HTTPException(status_code=404, detail="Document not found")
        await session.delete(doc)
    return {"deleted": document_id}


# ── Stats ──────────────────────────────────────────────────────────────────────

@app.get("/stats", response_model=StatsResponse)
async def stats() -> StatsResponse:
    async with get_async_session() as session:
        count = await session.scalar(
            select(func.count()).select_from(Document).where(Document.app_name == APP_NAME)
        )
    provider = settings.llm_provider
    model = settings.openai_chat_model if provider == "openai" else settings.anthropic_chat_model
    return StatsResponse(
        document_count=count or 0,
        llm_provider=provider,
        llm_model=model,
    )


# ── UI ─────────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def ui() -> HTMLResponse:
    return HTMLResponse(content=(_STATIC_DIR / "index.html").read_text(encoding="utf-8"))
