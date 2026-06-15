"""
Embedding generation — thin wrapper around the LLM provider.

Batches chunk embedding into a single API call to minimise cost.
Enforces the MAX_EMBEDDING_CALLS_PER_RUN cost control limit.
"""

from aiplatform.ingestion.chunker import TextChunk
from aiplatform.llm.base import EmbeddingResponse, LLMProvider
from aiplatform.settings import settings


class CostLimitExceeded(Exception):
    """Raised when an embedding run would exceed the configured cost cap."""


class Embedder:
    """Generate embeddings for text chunks using the configured LLM provider."""

    def __init__(self, provider: LLMProvider, run_limit: int | None = None) -> None:
        self._provider = provider
        self._limit = run_limit or settings.max_embedding_calls_per_run
        self._calls_made = 0

    async def embed_chunks(self, chunks: list[TextChunk]) -> list[EmbeddingResponse]:
        """
        Embed a list of chunks in a single batch API call.

        Counts as one call toward the run limit regardless of batch size,
        because the provider sends one request for the entire batch.
        """
        if not chunks:
            return []

        self._check_limit(1)
        responses = await self._provider.embed_batch([c.content for c in chunks])
        self._calls_made += 1
        return responses

    async def embed_query(self, query: str) -> EmbeddingResponse:
        """Embed a user query for similarity search."""
        self._check_limit(1)
        response = await self._provider.embed(query)
        self._calls_made += 1
        return response

    def _check_limit(self, additional: int) -> None:
        if self._calls_made + additional > self._limit:
            raise CostLimitExceeded(
                f"Embedding call limit reached: {self._calls_made}/{self._limit}. "
                "Raise MAX_EMBEDDING_CALLS_PER_RUN to process more documents per run."
            )

    @property
    def calls_made(self) -> int:
        return self._calls_made
