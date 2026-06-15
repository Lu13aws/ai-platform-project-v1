"""
LLM provider abstraction layer.

All LLM interactions in the platform go through LLMProvider.
No application code should import openai or anthropic directly.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import StrEnum


class LLMProviderName(StrEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


@dataclass(frozen=True)
class Message:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass(frozen=True)
class LLMResponse:
    content: str
    model: str
    input_tokens: int
    output_tokens: int
    provider: LLMProviderName

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class EmbeddingResponse:
    vector: list[float]
    model: str
    input_tokens: int
    provider: LLMProviderName


@dataclass
class LLMUsageStats:
    """Accumulated usage for a single run — enforce cost control limits against this."""

    total_llm_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_embedding_calls: int = 0
    total_embedding_tokens: int = 0
    providers_used: list[str] = field(default_factory=list)

    def record_llm(self, response: LLMResponse) -> None:
        self.total_llm_calls += 1
        self.total_input_tokens += response.input_tokens
        self.total_output_tokens += response.output_tokens
        if response.provider not in self.providers_used:
            self.providers_used.append(response.provider)

    def record_embedding(self, response: EmbeddingResponse) -> None:
        self.total_embedding_calls += 1
        self.total_embedding_tokens += response.input_tokens


class LLMProvider(ABC):
    """
    Abstract base for all LLM provider implementations.

    Rules:
    - Async-first: all methods are coroutines or async generators.
    - Stateless: no conversation history stored; callers manage history.
    - Cost-transparent: always return token counts in responses.
    """

    @abstractmethod
    async def complete(
        self,
        messages: list[Message],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        """Generate a single completion from a list of messages."""
        ...

    @abstractmethod
    async def complete_stream(
        self,
        messages: list[Message],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        """
        Stream a completion token by token.

        Token counts are not available for streamed responses.
        Use complete() when you need cost tracking.
        """
        ...

    @abstractmethod
    async def embed(self, text: str) -> EmbeddingResponse:
        """Generate an embedding vector for a single text."""
        ...

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[EmbeddingResponse]:
        """
        Generate embedding vectors for multiple texts in one API call.

        Prefer this over calling embed() in a loop.
        """
        ...

    @property
    @abstractmethod
    def provider_name(self) -> LLMProviderName:
        ...

    @property
    @abstractmethod
    def default_chat_model(self) -> str:
        ...

    @property
    @abstractmethod
    def default_embedding_model(self) -> str:
        ...

    async def health_check(self) -> bool:
        """Verify the provider API is reachable and credentials are valid."""
        try:
            await self.embed("health check")
            return True
        except Exception:
            return False
