"""
Content-hash-based deduplication for documents and chunks.

Computes a SHA-256 hash of raw content to detect unchanged documents
before re-embedding, avoiding unnecessary LLM API costs.
"""

import hashlib

from aiplatform.settings import settings


def hash_content(content: bytes | str) -> str:
    """Return a hex digest of the content using the configured hash algorithm."""
    raw = content if isinstance(content, bytes) else content.encode("utf-8")
    h = hashlib.new(settings.hash_algorithm)
    h.update(raw)
    return h.hexdigest()


def content_changed(new_hash: str, existing_hash: str | None) -> bool:
    """Return True if the content hash differs from the stored hash."""
    return existing_hash is None or new_hash != existing_hash
