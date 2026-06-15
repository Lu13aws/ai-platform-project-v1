"""
Document loader abstraction.

Implement in Phase 1.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class LoadedDocument:
    content: str
    source_uri: str
    mime_type: str
    metadata: dict = field(default_factory=dict)


class DocumentLoader(ABC):
    """Load a document from a path or URI and return its text content."""

    @abstractmethod
    async def load(self, source: str | Path) -> LoadedDocument:
        ...

    @abstractmethod
    def supports(self, source: str | Path) -> bool:
        """Return True if this loader can handle the given source."""
        ...
