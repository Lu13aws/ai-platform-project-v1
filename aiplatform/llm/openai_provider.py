from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from aiplatform.llm.base import (
    EmbeddingResponse,
    LLMProvider,
    LLMProviderName,
    LLMResponse,
    Message,
)


class OpenAIProvider(LLMProvider):
    def __init__(
        self,
        api_key: str,
        chat_model: str,
        embedding_model: str,
        temperature: float,
        max_tokens: int,
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._chat_model = chat_model
        self._embedding_model = embedding_model
        self._temperature = temperature
        self._max_tokens = max_tokens

    @property
    def provider_name(self) -> LLMProviderName:
        return LLMProviderName.OPENAI

    @property
    def default_chat_model(self) -> str:
        return self._chat_model

    @property
    def default_embedding_model(self) -> str:
        return self._embedding_model

    async def complete(
        self,
        messages: list[Message],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        oai_messages: list[dict[str, str]] = []
        if system_prompt:
            oai_messages.append({"role": "system", "content": system_prompt})
        oai_messages.extend({"role": m.role, "content": m.content} for m in messages)

        response = await self._client.chat.completions.create(
            model=self._chat_model,
            messages=oai_messages,  # type: ignore[arg-type]
            temperature=temperature if temperature is not None else self._temperature,
            max_tokens=max_tokens if max_tokens is not None else self._max_tokens,
        )
        usage = response.usage
        assert usage is not None
        return LLMResponse(
            content=response.choices[0].message.content or "",
            model=response.model,
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            provider=LLMProviderName.OPENAI,
        )

    async def complete_stream(
        self,
        messages: list[Message],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        oai_messages: list[dict[str, str]] = []
        if system_prompt:
            oai_messages.append({"role": "system", "content": system_prompt})
        oai_messages.extend({"role": m.role, "content": m.content} for m in messages)

        stream = await self._client.chat.completions.create(
            model=self._chat_model,
            messages=oai_messages,  # type: ignore[arg-type]
            temperature=temperature if temperature is not None else self._temperature,
            max_tokens=max_tokens if max_tokens is not None else self._max_tokens,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    async def embed(self, text: str) -> EmbeddingResponse:
        responses = await self.embed_batch([text])
        return responses[0]

    async def embed_batch(self, texts: list[str]) -> list[EmbeddingResponse]:
        if not texts:
            raise ValueError("texts must not be empty")

        # OpenAI limits: 300,000 tokens per request, 2,048 inputs per request.
        # Split into sub-batches of 100 to stay safely within both limits.
        _BATCH_SIZE = 100
        all_responses: list[EmbeddingResponse] = []

        for offset in range(0, len(texts), _BATCH_SIZE):
            batch = texts[offset : offset + _BATCH_SIZE]
            response = await self._client.embeddings.create(
                model=self._embedding_model,
                input=batch,
            )
            tokens_per_item = response.usage.total_tokens // len(batch)
            all_responses.extend(
                EmbeddingResponse(
                    vector=item.embedding,
                    model=response.model,
                    input_tokens=tokens_per_item,
                    provider=LLMProviderName.OPENAI,
                )
                for item in sorted(response.data, key=lambda x: x.index)
            )

        return all_responses
