"""Ingest must fail loudly when the embedder returns a different number of vectors than chunks."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiplatform.storage.models import Chunk, Embedding
from apps.rag_demo.api.schemas import IngestRequest
from apps.rag_demo.services import ingest_service
from apps.rag_demo.services.ingest_service import IngestService


def _vector() -> SimpleNamespace:
    return SimpleNamespace(vector=[0.0], model="m", provider=SimpleNamespace(value="p"))


def _rig(monkeypatch, tmp_path, embeddings_missing: int):
    class _FakeEmbedder:
        def __init__(self, _provider):
            pass

        async def embed_chunks(self, chunks):
            return [_vector() for _ in range(len(chunks) - embeddings_missing)]

    monkeypatch.setattr(ingest_service, "validate_source_path", lambda _uri: None)
    monkeypatch.setattr(ingest_service, "get_llm_provider", lambda: object())
    monkeypatch.setattr(ingest_service, "Embedder", _FakeEmbedder)

    doc = tmp_path / "doc.txt"
    doc.write_text("word " * 3000, encoding="utf-8")  # several chunks
    session = MagicMock()
    session.scalar = AsyncMock(return_value=None)  # not ingested before
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    return IngestService(session), session, IngestRequest(source_uri=str(doc))


async def test_ingest_stores_one_embedding_per_chunk(monkeypatch, tmp_path):
    service, session, request = _rig(monkeypatch, tmp_path, embeddings_missing=0)

    response = await service.ingest(request)

    added = [c.args[0] for c in session.add.call_args_list]
    chunks = [a for a in added if isinstance(a, Chunk)]
    embeddings = [a for a in added if isinstance(a, Embedding)]
    assert len(chunks) > 1
    assert len(embeddings) == len(chunks) == response.chunks_created


async def test_ingest_raises_instead_of_silently_dropping_embeddings(monkeypatch, tmp_path):
    """zip() without strict= used to truncate silently: chunks stored without a vector."""
    service, _session, request = _rig(monkeypatch, tmp_path, embeddings_missing=1)

    with pytest.raises(ValueError, match="zip"):
        await service.ingest(request)
