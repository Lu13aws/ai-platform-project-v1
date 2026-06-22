"""
Core service for the Corporate API — query, ingest, audit.

Uses the corp DB session (ai-platform-db-corp) — never touches the public DB.
"""

import hashlib
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aiplatform.ingestion.chunker import Chunker
from aiplatform.llm import get_llm_provider
from aiplatform.retrieval.embedder import Embedder
from aiplatform.retrieval.vector_store import VectorStore
from aiplatform.storage.corp_models import AuditLog
from aiplatform.storage.models import Chunk, Document, Embedding
from apps.corp_api.api.schemas import (
    AuditEntry,
    AuditResponse,
    IngestRequest,
    IngestResponse,
    QueryRequest,
    QueryResponse,
    SourceItem,
    SourceRef,
    SourcesResponse,
)
from apps.corp_api.auth.cognito import UserClaims

_CORP_SYSTEM_PROMPT = """\
You are a knowledgeable assistant for the AI Knowledge Platform corporate demo.
Answer questions using only the provided context from internal documents.
Cite your sources by referencing the [1], [2], etc. labels in your response.
If the context does not contain sufficient information, say so clearly — do not speculate.\
"""


async def query_corp(
    session: AsyncSession,
    request: QueryRequest,
    user: UserClaims,
    client_ip: str | None = None,
) -> QueryResponse:
    provider = get_llm_provider()
    embedder = Embedder(provider)

    query_embedding = await embedder.embed_query(request.question)

    store = VectorStore(session)
    results = await store.search(
        query_embedding.vector,
        top_k=request.top_k,
        app_name="corp",
    )

    if not results:
        await _log(session, user, "query", detail=f"q={request.question[:100]} | no results", ip=client_ip)
        return QueryResponse(
            answer="No relevant documents found. Make sure corporate documents have been ingested.",
            sources=[],
            user_id=user.user_id,
        )

    context_parts = []
    source_refs = []
    for i, r in enumerate(results, 1):
        context_parts.append(f"[{i}] {r.content}")
        source_refs.append(SourceRef(
            title=r.title,
            source_uri=r.source_uri,
            similarity=round(r.similarity, 3),
        ))

    context = "\n\n".join(context_parts)
    messages = [
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {request.question}"},
    ]
    response = await provider.chat(messages=messages, system=_CORP_SYSTEM_PROMPT)

    await _log(
        session, user, "query",
        resource=f"{len(results)} chunks",
        detail=f"q={request.question[:100]}",
        ip=client_ip,
    )

    return QueryResponse(
        answer=response.content,
        sources=source_refs,
        user_id=user.user_id,
    )


async def ingest_corp(
    session: AsyncSession,
    request: IngestRequest,
    user: UserClaims,
    client_ip: str | None = None,
) -> IngestResponse:
    content_hash = hashlib.sha256(request.content.encode()).hexdigest()

    # Check for existing document by source_uri
    existing = await session.scalar(
        select(Document).where(Document.source_uri == request.source_uri)
    )
    if existing:
        if existing.content_hash == content_hash:
            await _log(session, user, "ingest_skip", resource=request.source_uri, ip=client_ip)
            return IngestResponse(
                document_id=existing.id,
                skipped=True,
                message="Content unchanged — skipped.",
            )
        # Content changed — delete and re-index
        await session.delete(existing)
        await session.flush()

    provider = get_llm_provider()
    embedder = Embedder(provider)
    chunker = Chunker()

    chunks = chunker.split(request.content)

    doc = Document(
        source_uri=request.source_uri,
        content_hash=content_hash,
        title=request.title or request.source_uri.split("/")[-1],
        mime_type="text/plain",
        doc_metadata={"ingested_by": user.email},
        app_name=request.app_name,
    )
    session.add(doc)
    await session.flush()

    for idx, chunk_text in enumerate(chunks):
        chunk = Chunk(
            document_id=doc.id,
            chunk_index=idx,
            content=chunk_text,
            content_hash=hashlib.sha256(chunk_text.encode()).hexdigest(),
            token_count=len(chunk_text.split()),
            chunk_metadata={},
        )
        session.add(chunk)
        await session.flush()

        embedding_result = await embedder.embed_query(chunk_text)
        emb = Embedding(
            chunk_id=chunk.id,
            vector=embedding_result.vector,
            model=provider.default_embedding_model,
            provider=provider.name,
        )
        session.add(emb)

    await _log(
        session, user, "ingest",
        resource=request.source_uri,
        detail=f"{len(chunks)} chunks",
        ip=client_ip,
    )

    return IngestResponse(
        document_id=doc.id,
        skipped=False,
        message=f"Ingested {len(chunks)} chunks.",
    )


async def get_sources(session: AsyncSession) -> SourcesResponse:
    result = await session.execute(
        select(Document)
        .where(Document.app_name == "corp")
        .order_by(Document.created_at.desc())
    )
    docs = result.scalars().all()
    items = [
        SourceItem(
            id=d.id,
            title=d.title,
            source_uri=d.source_uri,
            app_name=d.app_name,
            created_at=d.created_at,
        )
        for d in docs
    ]
    return SourcesResponse(total=len(items), sources=items)


async def get_audit_log(
    session: AsyncSession,
    limit: int = 100,
) -> AuditResponse:
    result = await session.execute(
        select(AuditLog)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    entries = result.scalars().all()
    return AuditResponse(
        total=len(entries),
        entries=[
            AuditEntry(
                id=e.id,
                user_id=e.user_id,
                email=e.email,
                action=e.action,
                resource=e.resource,
                detail=e.detail,
                ip_address=e.ip_address,
                created_at=e.created_at,
            )
            for e in entries
        ],
    )


async def _log(
    session: AsyncSession,
    user: UserClaims,
    action: str,
    resource: str | None = None,
    detail: str | None = None,
    ip: str | None = None,
) -> None:
    entry = AuditLog(
        user_id=user.user_id,
        email=user.email,
        action=action,
        resource=resource,
        detail=detail,
        ip_address=ip,
    )
    session.add(entry)
