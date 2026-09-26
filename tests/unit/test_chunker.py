import pytest

from aiplatform.ingestion.chunker import Chunker
from aiplatform.settings import settings


def test_split_basic():
    chunker = Chunker(chunk_size=50, chunk_overlap=10)
    text = "This is a sentence. " * 50
    chunks = chunker.split(text)
    assert len(chunks) > 1
    assert all(c.token_count > 0 for c in chunks)
    assert all(c.chunk_index == i for i, c in enumerate(chunks))


def test_split_empty_text_returns_empty():
    chunker = Chunker()
    assert chunker.split("") == []
    assert chunker.split("   ") == []


def test_split_short_text_is_single_chunk():
    chunker = Chunker(chunk_size=200, chunk_overlap=20)
    text = "Short document."
    chunks = chunker.split(text)
    assert len(chunks) == 1
    assert chunks[0].content == "Short document."
    assert chunks[0].chunk_index == 0


def test_split_passes_metadata_to_all_chunks():
    chunker = Chunker(chunk_size=50, chunk_overlap=5)
    text = "Word " * 200
    meta = {"source": "test.pdf"}
    chunks = chunker.split(text, metadata=meta)
    assert all(c.metadata["source"] == "test.pdf" for c in chunks)


def test_split_raises_when_chunk_limit_exceeded(monkeypatch):
    # Pin the limit: the real value comes from MAX_CHUNKS_PER_DOC in the local .env / environment.
    monkeypatch.setattr(settings, "max_chunks_per_doc", 100)
    chunker = Chunker(chunk_size=10, chunk_overlap=2)
    # Tiny chunk size + long text → far more than 100 chunks
    text = "word " * 5000
    with pytest.raises(ValueError, match="exceeding the limit"):
        chunker.split(text)


def test_token_count_is_positive():
    chunker = Chunker(chunk_size=100, chunk_overlap=10)
    chunks = chunker.split("The quick brown fox jumps over the lazy dog. " * 20)
    assert all(c.token_count > 0 for c in chunks)
