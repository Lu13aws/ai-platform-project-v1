"""
Shared pytest fixtures.

Unit tests: use mock_settings and mock_llm_provider — no I/O.
Integration tests: use db_session — requires Docker (make dev-up + make migrate).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiplatform.llm.base import EmbeddingResponse, LLMProvider, LLMProviderName, LLMResponse


@pytest.fixture(autouse=False)
def mock_settings(monkeypatch):
    """Override settings with safe test defaults — no real API keys or DB."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://aiplatform:aiplatform@localhost:5432/aiplatform_test")
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", "postgresql://aiplatform:aiplatform@localhost:5432/aiplatform_test")

    from aiplatform.settings import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def mock_llm_provider() -> LLMProvider:
    """A mock LLM provider that returns canned responses without hitting any API."""
    provider = MagicMock(spec=LLMProvider)
    provider.provider_name = LLMProviderName.OPENAI
    provider.default_chat_model = "gpt-4o-mini"
    provider.default_embedding_model = "text-embedding-3-small"

    provider.complete = AsyncMock(return_value=LLMResponse(
        content="This is a test answer.",
        model="gpt-4o-mini",
        input_tokens=50,
        output_tokens=10,
        provider=LLMProviderName.OPENAI,
    ))

    provider.embed = AsyncMock(return_value=EmbeddingResponse(
        vector=[0.1] * 1536,
        model="text-embedding-3-small",
        input_tokens=5,
        provider=LLMProviderName.OPENAI,
    ))

    provider.embed_batch = AsyncMock(side_effect=lambda texts: [
        EmbeddingResponse(
            vector=[0.1] * 1536,
            model="text-embedding-3-small",
            input_tokens=5,
            provider=LLMProviderName.OPENAI,
        )
        for _ in texts
    ])

    return provider
