"""
Integration test for VectorStore — requires Docker DB (make dev-up + make migrate).
"""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from aiplatform.retrieval.vector_store import VectorStore
from aiplatform.settings import settings
from aiplatform.storage.models import Chunk, Document, Embedding


@pytest.fixture
async def db_session():
    engine = create_async_engine(settings.database_url, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        yield session
        await session.rollback()  # clean up — never commit test data
    await engine.dispose()


async def _insert_test_data(session: AsyncSession, vector: list[float], app: str) -> tuple:
    doc = Document(
        id=uuid4(),
        source_uri=f"test://doc-{uuid4()}",
        content_hash=str(uuid4()),
        mime_type="text/plain",
        doc_metadata={},
        app_name=app,
    )
    session.add(doc)
    await session.flush()

    chunk = Chunk(
        id=uuid4(),
        document_id=doc.id,
        chunk_index=0,
        content="This is a test chunk about OWASP security.",
        content_hash=str(uuid4()),
        token_count=10,
        chunk_metadata={},
    )
    session.add(chunk)
    await session.flush()

    embedding = Embedding(
        id=uuid4(),
        chunk_id=chunk.id,
        vector=vector,
        model="text-embedding-3-small",
        provider="openai",
    )
    session.add(embedding)
    await session.flush()

    return doc, chunk, embedding


async def test_search_returns_similar_chunk(db_session):
    # Insert a chunk with a known vector
    query_vector = [0.1] * 1536
    await _insert_test_data(db_session, query_vector, app="rag_demo")

    store = VectorStore(db_session)
    results = await store.search(query_vector, top_k=5, similarity_threshold=0.5)

    assert len(results) >= 1
    assert results[0].score > 0.5
    assert "OWASP" in results[0].content


async def test_search_filters_by_app_name(db_session):
    vector = [0.2] * 1536
    await _insert_test_data(db_session, vector, app="rag_demo")
    await _insert_test_data(db_session, vector, app="tech_radar")

    store = VectorStore(db_session)

    rag_results = await store.search(vector, app_name="rag_demo", similarity_threshold=0.5)
    radar_results = await store.search(vector, app_name="tech_radar", similarity_threshold=0.5)

    assert all(r.source_uri for r in rag_results)
    assert all(r.source_uri for r in radar_results)
    # Each app only sees its own documents
    assert len(rag_results) >= 1
    assert len(radar_results) >= 1


async def test_search_returns_empty_below_threshold(db_session):
    # Insert with a very different vector
    stored_vector = [1.0] + [0.0] * 1535
    query_vector = [0.0] * 1535 + [1.0]
    await _insert_test_data(db_session, stored_vector, app="rag_demo")

    store = VectorStore(db_session)
    results = await store.search(query_vector, similarity_threshold=0.99)

    assert results == []


async def test_search_respects_top_k(db_session):
    vector = [0.3] * 1536
    for _ in range(5):
        await _insert_test_data(db_session, vector, app="rag_demo")

    store = VectorStore(db_session)
    results = await store.search(vector, top_k=2, similarity_threshold=0.5)

    assert len(results) <= 2
