from collections.abc import AsyncIterator

import anthropic

from aiplatform.llm.base import (
    EmbeddingResponse,
    LLMProvider,
    LLMProviderName,
    LLMResponse,
    Message,
)

# Anthropic does not offer an embedding API — embeddings must use OpenAI or another provider.
# Calling embed() on this provider raises NotImplementedError.
_NO_EMBEDDING_MSG = (
    "Anthropic does not provide an embedding API. "
    "Set LLM_PROVIDER=openai or configure a dedicated embedding provider."
)


class AnthropicProvider(LLMProvider):
    def __init__(
        self,
        api_key: str,
        chat_model: str,
        temperature: float,
        max_tokens: int,
    ) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._chat_model = chat_model
        self._temperature = temperature
        self._max_tokens = max_tokens

    @property
    def provider_name(self) -> LLMProviderName:
        return LLMProviderName.ANTHROPIC

    @property
    def default_chat_model(self) -> str:
        return self._chat_model

    @property
    def default_embedding_model(self) -> str:
        raise NotImplementedError(_NO_EMBEDDING_MSG)

    async def complete(
        self,
        messages: list[Message],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        anthropic_messages = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role != "system"
        ]

        kwargs: dict = {
            "model": self._chat_model,
            "messages": anthropic_messages,
            "temperature": temperature if temperature is not None else self._temperature,
            "max_tokens": max_tokens if max_tokens is not None else self._max_tokens,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        elif any(m.role == "system" for m in messages):
            # Extract system message from messages list if present
            kwargs["system"] = next(m.content for m in messages if m.role == "system")

        response = await self._client.messages.create(**kwargs)
        usage = response.usage
        content_block = response.content[0]
        text = content_block.text if hasattr(content_block, "text") else ""

        return LLMResponse(
            content=text,
            model=response.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            provider=LLMProviderName.ANTHROPIC,
        )

    async def complete_stream(
        self,
        messages: list[Message],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        anthropic_messages = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role != "system"
        ]

        kwargs: dict = {
            "model": self._chat_model,
            "messages": anthropic_messages,
            "temperature": temperature if temperature is not None else self._temperature,
            "max_tokens": max_tokens if max_tokens is not None else self._max_tokens,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        elif any(m.role == "system" for m in messages):
            kwargs["system"] = next(m.content for m in messages if m.role == "system")

        async with self._client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text

    async def embed(self, text: str) -> EmbeddingResponse:
        raise NotImplementedError(_NO_EMBEDDING_MSG)

    async def embed_batch(self, texts: list[str]) -> list[EmbeddingResponse]:
        raise NotImplementedError(_NO_EMBEDDING_MSG)

    async def health_check(self) -> bool:
        """Use a minimal message call instead of embed (which is not supported)."""
        try:
            await self._client.messages.create(
                model=self._chat_model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
            )
            return True
        except Exception:
            return False
