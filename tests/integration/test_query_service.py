"""
Integration tests for QueryService — requires Docker DB (make dev-up + make migrate).
LLM provider is mocked to avoid real API calls.
"""

from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from aiplatform.settings import settings
from aiplatform.storage.models import Chunk, Document, Embedding
from apps.rag_demo.api.schemas import QueryRequest
from apps.rag_demo.services.query_service import APP_NAME, QueryService


@pytest.fixture
async def db_session():
    engine = create_async_engine(settings.database_url, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        yield session
        await session.rollback()
    await engine.dispose()


async def _seed_document(session: AsyncSession, content: str, vector: list[float]) -> None:
    """Insert one document with one chunk and one embedding."""
    doc_id = uuid4()
    session.add(
        Document(
            id=doc_id,
            source_uri=f"test://seed-{doc_id}",
            content_hash=str(uuid4()),
            mime_type="text/plain",
            doc_metadata={},
            app_name=APP_NAME,
        )
    )
    await session.flush()

    chunk_id = uuid4()
    session.add(
        Chunk(
            id=chunk_id,
            document_id=doc_id,
            chunk_index=0,
            content=content,
            content_hash=str(uuid4()),
            token_count=len(content.split()),
            chunk_metadata={},
        )
    )
    await session.flush()

    session.add(
        Embedding(
            id=uuid4(),
            chunk_id=chunk_id,
            vector=vector,
            model="text-embedding-3-small",
            provider="openai",
        )
    )
    await session.flush()


async def test_query_returns_answer_with_sources(db_session, mock_llm_provider):
    vector = [0.1] * 1536
    await _seed_document(db_session, "OWASP Top 10 describes web security risks.", vector)

    with patch("apps.rag_demo.services.query_service.get_llm_provider", return_value=mock_llm_provider):
        result = await QueryService(db_session).query(
            QueryRequest(question="What is OWASP?", top_k=3)
        )

    assert result.answer == "This is a test answer."
    assert len(result.sources) >= 1
    assert result.model == "gpt-4o-mini"
    assert result.input_tokens > 0 or result.output_tokens > 0


async def test_query_returns_no_results_message_when_empty(db_session, mock_llm_provider):
    # Use a vector that won't match anything in the DB
    from unittest.mock import AsyncMock
    from aiplatform.llm.base import EmbeddingResponse, LLMProviderName

    # Override embed to return a very unique vector unlikely to match
    mock_llm_provider.embed = AsyncMock(return_value=EmbeddingResponse(
        vector=[0.999] * 1536,
        model="text-embedding-3-small",
        input_tokens=5,
        provider=LLMProviderName.OPENAI,
    ))

    with patch("apps.rag_demo.services.query_service.get_llm_provider", return_value=mock_llm_provider):
        result = await QueryService(db_session).query(
            QueryRequest(question="A very obscure question with no matching content", top_k=3)
        )

    # Should short-circuit without calling LLM
    assert result.sources == []
    assert "could not find" in result.answer.lower()
    assert result.input_tokens == 0
    assert result.output_tokens == 0


async def test_query_sources_include_score_and_excerpt(db_session, mock_llm_provider):
    vector = [0.2] * 1536
    await _seed_document(db_session, "NIST frameworks define cybersecurity best practices.", vector)

    with patch("apps.rag_demo.services.query_service.get_llm_provider", return_value=mock_llm_provider):
        result = await QueryService(db_session).query(
            QueryRequest(question="Tell me about NIST", top_k=5)
        )

    for source in result.sources:
        assert 0.0 <= source.score <= 1.0
        assert len(source.excerpt) > 0
        assert source.chunk_id is not None
        assert source.source_uri.startswith("test://")
