"""
Integration tests for IngestService — requires Docker DB (make dev-up + make migrate).
LLM provider is mocked to avoid real API calls.
"""

from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from aiplatform.settings import settings
from aiplatform.storage.models import Chunk, Document, Embedding
from apps.rag_demo.api.schemas import IngestRequest
from apps.rag_demo.services.ingest_service import APP_NAME, IngestService


@pytest.fixture
async def db_session():
    engine = create_async_engine(settings.database_url, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        yield session
        await session.rollback()
    await engine.dispose()


async def test_ingest_new_document(db_session, mock_llm_provider, tmp_path):
    doc_path = tmp_path / "sample.txt"
    doc_path.write_text("OWASP Top 10 describes the most critical web application security risks.")

    with patch("apps.rag_demo.services.ingest_service.get_llm_provider", return_value=mock_llm_provider):
        result = await IngestService(db_session).ingest(
            IngestRequest(source_uri=str(doc_path))
        )

    assert result.skipped is False
    assert result.chunks_created >= 1
    assert result.document_id is not None

    doc = await db_session.scalar(
        select(Document).where(Document.source_uri == str(doc_path))
    )
    assert doc is not None
    assert doc.app_name == APP_NAME


async def test_ingest_skips_unchanged_document(db_session, mock_llm_provider, tmp_path):
    doc_path = tmp_path / "sample.txt"
    doc_path.write_text("Unchanged content for deduplication test.")

    with patch("apps.rag_demo.services.ingest_service.get_llm_provider", return_value=mock_llm_provider):
        service = IngestService(db_session)
        first = await service.ingest(IngestRequest(source_uri=str(doc_path)))
        second = await service.ingest(IngestRequest(source_uri=str(doc_path)))

    assert first.skipped is False
    assert second.skipped is True
    assert second.document_id == first.document_id
    assert "unchanged" in second.message.lower()


async def test_ingest_reprocesses_changed_document(db_session, mock_llm_provider, tmp_path):
    doc_path = tmp_path / "sample.txt"
    doc_path.write_text("Version 1 of this document.")

    with patch("apps.rag_demo.services.ingest_service.get_llm_provider", return_value=mock_llm_provider):
        service = IngestService(db_session)
        first = await service.ingest(IngestRequest(source_uri=str(doc_path)))

        # Update the file content
        doc_path.write_text("Version 2: content has changed significantly.", encoding="utf-8")
        second = await service.ingest(IngestRequest(source_uri=str(doc_path)))

    assert first.skipped is False
    assert second.skipped is False
    assert second.document_id != first.document_id


async def test_ingest_stores_chunks_and_embeddings(db_session, mock_llm_provider, tmp_path):
    doc_path = tmp_path / "sample.txt"
    doc_path.write_text("Testing that chunks and embeddings are stored correctly in the database.")

    with patch("apps.rag_demo.services.ingest_service.get_llm_provider", return_value=mock_llm_provider):
        result = await IngestService(db_session).ingest(
            IngestRequest(source_uri=str(doc_path))
        )

    # Verify chunks exist in DB
    chunks = (
        await db_session.execute(
            select(Chunk).join(Document).where(Document.source_uri == str(doc_path))
        )
    ).scalars().all()
    assert len(chunks) == result.chunks_created

    # Verify each chunk has an embedding
    for chunk in chunks:
        embedding = await db_session.scalar(
            select(Embedding).where(Embedding.chunk_id == chunk.id)
        )
        assert embedding is not None
        assert len(embedding.vector) == 1536


async def test_ingest_skips_identical_content_different_source(db_session, mock_llm_provider, tmp_path):
    content = "This exact content will be used from two different file paths."
    path_a = tmp_path / "a.txt"
    path_b = tmp_path / "b.txt"
    path_a.write_text(content)
    path_b.write_text(content)

    with patch("apps.rag_demo.services.ingest_service.get_llm_provider", return_value=mock_llm_provider):
        service = IngestService(db_session)
        first = await service.ingest(IngestRequest(source_uri=str(path_a)))
        second = await service.ingest(IngestRequest(source_uri=str(path_b)))

    assert first.skipped is False
    assert second.skipped is True
    assert second.document_id == first.document_id
