from pydantic import BaseModel, Field


class IngestRequest(BaseModel):
    source_uri: str = Field(..., description="Path or URL to the document to ingest")
    title: str | None = None
    metadata: dict = Field(default_factory=dict)


class IngestResponse(BaseModel):
    document_id: str
    chunks_created: int
    skipped: bool = False
    message: str


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)


class SourceReference(BaseModel):
    chunk_id: str
    source_uri: str
    score: float
    excerpt: str


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceReference]
    model: str
    input_tokens: int
    output_tokens: int
