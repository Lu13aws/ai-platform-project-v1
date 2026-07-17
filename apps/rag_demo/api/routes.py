from aiplatform.auth.cognito import get_current_user
from aiplatform.retrieval.embedder import CostLimitExceeded
from aiplatform.storage.database import get_session
from apps.rag_demo.api.schemas import (
    IngestRequest,
    IngestResponse,
    QueryRequest,
    QueryResponse,
)
from apps.rag_demo.services.ingest_service import IngestService
from apps.rag_demo.services.query_service import QueryService
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.post("/ingest", response_model=IngestResponse, dependencies=[Depends(get_current_user)])
async def ingest_document(
    request: IngestRequest,
    session: AsyncSession = Depends(get_session),
) -> IngestResponse:
    """Ingest a document: load → chunk → embed → store."""
    try:
        return await IngestService(session).ingest(request)
    except CostLimitExceeded as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.post("/query", response_model=QueryResponse)
async def query_documents(
    request: QueryRequest,
    session: AsyncSession = Depends(get_session),
) -> QueryResponse:
    """Answer a question using retrieved context and the configured LLM."""
    try:
        return await QueryService(session).query(request)
    except CostLimitExceeded as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
