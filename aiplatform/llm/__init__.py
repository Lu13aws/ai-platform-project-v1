from aiplatform.llm.anthropic_provider import AnthropicProvider
from aiplatform.llm.base import (
    EmbeddingResponse,
    LLMProvider,
    LLMProviderName,
    LLMResponse,
    LLMUsageStats,
    Message,
)
from aiplatform.llm.openai_provider import OpenAIProvider


def get_llm_provider(provider_name: LLMProviderName | str | None = None) -> LLMProvider:
    """
    Factory function that returns the correct LLMProvider based on settings.

    Usage:
        llm = get_llm_provider()            # reads from settings
        llm = get_llm_provider("anthropic") # explicit override
    """
    from aiplatform.settings import settings  # local import avoids circular dependency

    name = LLMProviderName(provider_name or settings.llm_provider)

    match name:
        case LLMProviderName.OPENAI:
            return OpenAIProvider(
                api_key=settings.openai_api_key.get_secret_value(),
                chat_model=settings.openai_chat_model,
                embedding_model=settings.openai_embedding_model,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
            )
        case LLMProviderName.ANTHROPIC:
            return AnthropicProvider(
                api_key=settings.anthropic_api_key.get_secret_value(),
                chat_model=settings.anthropic_chat_model,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
            )
        case _:
            raise ValueError(f"Unknown LLM provider: {name}")


__all__ = [
    "LLMProvider",
    "LLMProviderName",
    "LLMResponse",
    "EmbeddingResponse",
    "LLMUsageStats",
    "Message",
    "AnthropicProvider",
    "OpenAIProvider",
    "get_llm_provider",
]
