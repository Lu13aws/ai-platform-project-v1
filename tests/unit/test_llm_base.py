import pytest
from aiplatform.llm.base import (
    EmbeddingResponse,
    LLMProviderName,
    LLMResponse,
    LLMUsageStats,
    Message,
)


def test_llm_response_total_tokens():
    r = LLMResponse(
        content="hello",
        model="gpt-4o-mini",
        input_tokens=10,
        output_tokens=5,
        provider=LLMProviderName.OPENAI,
    )
    assert r.total_tokens == 15


def test_usage_stats_record_llm():
    stats = LLMUsageStats()
    r = LLMResponse(
        content="hello",
        model="gpt-4o-mini",
        input_tokens=100,
        output_tokens=20,
        provider=LLMProviderName.OPENAI,
    )
    stats.record_llm(r)
    assert stats.total_llm_calls == 1
    assert stats.total_input_tokens == 100
    assert stats.total_output_tokens == 20
    assert LLMProviderName.OPENAI in stats.providers_used


def test_usage_stats_record_embedding():
    stats = LLMUsageStats()
    e = EmbeddingResponse(
        vector=[0.1] * 1536,
        model="text-embedding-3-small",
        input_tokens=8,
        provider=LLMProviderName.OPENAI,
    )
    stats.record_embedding(e)
    assert stats.total_embedding_calls == 1
    assert stats.total_embedding_tokens == 8


def test_message_is_frozen():
    from dataclasses import FrozenInstanceError

    m = Message(role="user", content="hello")
    with pytest.raises(FrozenInstanceError):
        m.role = "assistant"  # type: ignore[misc]


async def test_mock_provider_complete(mock_llm_provider):
    response = await mock_llm_provider.complete([Message(role="user", content="test")])
    assert response.content == "This is a test answer."
    assert response.total_tokens == 60


async def test_mock_provider_embed_batch(mock_llm_provider):
    texts = ["text one", "text two", "text three"]
    responses = await mock_llm_provider.embed_batch(texts)
    assert len(responses) == 3
    assert all(len(r.vector) == 1536 for r in responses)
