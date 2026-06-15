"""
Text chunking using RecursiveCharacterTextSplitter with tiktoken-based token counting.
"""

from dataclasses import dataclass, field

import tiktoken
from langchain_text_splitters import RecursiveCharacterTextSplitter

from aiplatform.settings import settings


@dataclass
class TextChunk:
    content: str
    chunk_index: int
    token_count: int
    metadata: dict = field(default_factory=dict)


def _count_tokens(text: str, encoder: tiktoken.Encoding) -> int:
    return len(encoder.encode(text))


class Chunker:
    """Split document text into overlapping chunks sized by token count."""

    def __init__(
        self,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> None:
        self.chunk_size = chunk_size or settings.chunk_size
        self.chunk_overlap = chunk_overlap or settings.chunk_overlap
        self._encoder = tiktoken.get_encoding("cl100k_base")
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=lambda t: _count_tokens(t, self._encoder),
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    def split(self, text: str, metadata: dict | None = None) -> list[TextChunk]:
        """
        Split text into chunks.

        Raises ValueError if the document produces more chunks than
        settings.max_chunks_per_doc — safety cap against runaway costs.
        """
        if not text.strip():
            return []

        raw_chunks = self._splitter.split_text(text)

        if len(raw_chunks) > settings.max_chunks_per_doc:
            raise ValueError(
                f"Document produced {len(raw_chunks)} chunks, "
                f"exceeding the limit of {settings.max_chunks_per_doc}. "
                "Split the document or raise MAX_CHUNKS_PER_DOC."
            )

        base_metadata = metadata or {}
        return [
            TextChunk(
                content=chunk,
                chunk_index=i,
                token_count=_count_tokens(chunk, self._encoder),
                metadata=base_metadata,
            )
            for i, chunk in enumerate(raw_chunks)
        ]
