from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from aiplatform.storage.corp_db import get_corp_session_dep
from apps.corp_api.api.schemas import (
    AuditResponse,
    DeleteDocumentResponse,
    HealthResponse,
    IngestRequest,
    IngestResponse,
    QueryRequest,
    QueryResponse,
    SourcesResponse,
)
from apps.corp_api.auth.cognito import UserClaims, get_current_user, require_admin
from apps.corp_api.services.corp_service import (
    delete_document,
    get_audit_log,
    get_sources,
    ingest_corp,
    query_corp,
)

router = APIRouter(prefix="/corp", tags=["corporate"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", app="AI Knowledge Platform — Corporate")


@router.get("/health/auth", response_model=HealthResponse)
async def health_auth(user: UserClaims = Depends(get_current_user)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        app="AI Knowledge Platform — Corporate",
        authenticated=True,
        user_email=user.email,
    )


@router.post("/query", response_model=QueryResponse)
async def query(
    request: QueryRequest,
    req: Request,
    user: UserClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_corp_session_dep),
) -> QueryResponse:
    client_ip = req.client.host if req.client else None
    return await query_corp(session, request, user, client_ip)


@router.post("/ingest", response_model=IngestResponse)
async def ingest(
    request: IngestRequest,
    req: Request,
    user: UserClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_corp_session_dep),
) -> IngestResponse:
    client_ip = req.client.host if req.client else None
    return await ingest_corp(session, request, user, client_ip)


@router.get("/sources", response_model=SourcesResponse)
async def sources(
    _: UserClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_corp_session_dep),
) -> SourcesResponse:
    return await get_sources(session)


@router.delete("/documents/{document_id}", response_model=DeleteDocumentResponse)
async def delete_doc(
    document_id: UUID,
    req: Request,
    user: UserClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_corp_session_dep),
) -> DeleteDocumentResponse:
    client_ip = req.client.host if req.client else None
    result = await delete_document(session, document_id, user, client_ip)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found.")
    return result


@router.get("/audit", response_model=AuditResponse)
async def audit(
    limit: int = 100,
    user_id: str | None = None,
    _: UserClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_corp_session_dep),
) -> AuditResponse:
    return await get_audit_log(session, limit=limit, user_id=user_id)
