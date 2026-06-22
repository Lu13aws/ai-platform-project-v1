from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)


class SourceRef(BaseModel):
    title: str | None
    source_uri: str
    similarity: float


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceRef]
    user_id: str
    query_logged: bool = True


class IngestRequest(BaseModel):
    source_uri: str = Field(..., description="S3 URI or file path of the document")
    title: str | None = None
    content: str = Field(..., min_length=10)
    app_name: str = Field(default="corp", description="Namespace for this document")


class IngestResponse(BaseModel):
    document_id: UUID | None = None
    skipped: bool = False
    message: str


class AuditEntry(BaseModel):
    id: UUID
    user_id: str
    email: str
    action: str
    resource: str | None
    detail: str | None
    ip_address: str | None
    created_at: datetime


class AuditResponse(BaseModel):
    total: int
    entries: list[AuditEntry]


class SourceItem(BaseModel):
    id: UUID
    title: str | None
    source_uri: str
    app_name: str
    created_at: datetime


class SourcesResponse(BaseModel):
    total: int
    sources: list[SourceItem]


class DeleteDocumentResponse(BaseModel):
    document_id: UUID
    source_uri: str
    chunks_deleted: int
    message: str


class HealthResponse(BaseModel):
    status: str
    app: str
    authenticated: bool = False
    user_email: str | None = None
