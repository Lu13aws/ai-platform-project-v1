import pytest
from aiplatform.ingestion.chunker import TextChunk
from aiplatform.retrieval.embedder import CostLimitExceeded, Embedder


def make_chunk(content: str, index: int = 0) -> TextChunk:
    return TextChunk(content=content, chunk_index=index, token_count=len(content.split()), metadata={})


async def test_embed_chunks_calls_provider(mock_llm_provider):
    embedder = Embedder(mock_llm_provider)
    chunks = [make_chunk("hello world", 0), make_chunk("second chunk", 1)]
    responses = await embedder.embed_chunks(chunks)
    assert len(responses) == 2
    mock_llm_provider.embed_batch.assert_called_once_with(["hello world", "second chunk"])


async def test_embed_query_calls_provider(mock_llm_provider):
    embedder = Embedder(mock_llm_provider)
    response = await embedder.embed_query("What is OWASP?")
    assert len(response.vector) == 1536
    mock_llm_provider.embed.assert_called_once_with("What is OWASP?")


async def test_embed_chunks_empty_returns_empty(mock_llm_provider):
    embedder = Embedder(mock_llm_provider)
    result = await embedder.embed_chunks([])
    assert result == []
    mock_llm_provider.embed_batch.assert_not_called()


async def test_cost_limit_enforced(mock_llm_provider):
    embedder = Embedder(mock_llm_provider, run_limit=2)
    await embedder.embed_query("query 1")
    await embedder.embed_query("query 2")
    with pytest.raises(CostLimitExceeded, match="Embedding call limit reached"):
        await embedder.embed_query("query 3")


async def test_calls_made_tracks_count(mock_llm_provider):
    embedder = Embedder(mock_llm_provider, run_limit=10)
    await embedder.embed_query("q1")
    await embedder.embed_chunks([make_chunk("chunk")])
    assert embedder.calls_made == 2
