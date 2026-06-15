"""
Concrete document loaders for PDF, DOCX, TXT, Markdown, HTML, CSV, JSON.
"""

import csv
import json
from io import StringIO
from pathlib import Path

from aiplatform.ingestion.base import DocumentLoader, LoadedDocument


class PDFLoader(DocumentLoader):
    async def load(self, source: str | Path) -> LoadedDocument:
        from pypdf import PdfReader

        path = Path(source)
        reader = PdfReader(str(path))
        pages = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            if text.strip():
                pages.append(text)

        return LoadedDocument(
            content="\n\n".join(pages),
            source_uri=str(path),
            mime_type="application/pdf",
            metadata={
                "page_count": len(reader.pages),
                "filename": path.name,
            },
        )

    def supports(self, source: str | Path) -> bool:
        return str(source).lower().endswith(".pdf")


class DOCXLoader(DocumentLoader):
    async def load(self, source: str | Path) -> LoadedDocument:
        from docx import Document

        path = Path(source)
        doc = Document(str(path))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]

        return LoadedDocument(
            content="\n\n".join(paragraphs),
            source_uri=str(path),
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            metadata={
                "paragraph_count": len(paragraphs),
                "filename": path.name,
            },
        )

    def supports(self, source: str | Path) -> bool:
        return str(source).lower().endswith(".docx")


class TextLoader(DocumentLoader):
    """Handles .txt and .md files."""

    async def load(self, source: str | Path) -> LoadedDocument:
        path = Path(source)
        content = path.read_text(encoding="utf-8")
        suffix = path.suffix.lower()
        mime_type = "text/markdown" if suffix == ".md" else "text/plain"

        return LoadedDocument(
            content=content,
            source_uri=str(path),
            mime_type=mime_type,
            metadata={"filename": path.name},
        )

    def supports(self, source: str | Path) -> bool:
        return str(source).lower().endswith((".txt", ".md"))


class HTMLLoader(DocumentLoader):
    async def load(self, source: str | Path) -> LoadedDocument:
        from bs4 import BeautifulSoup

        path = Path(source)
        html = path.read_text(encoding="utf-8")
        soup = BeautifulSoup(html, "lxml")

        # Remove script and style elements
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        title = soup.title.string.strip() if soup.title and soup.title.string else path.name
        text = soup.get_text(separator="\n")
        # Collapse excessive blank lines
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        content = "\n".join(lines)

        return LoadedDocument(
            content=content,
            source_uri=str(path),
            mime_type="text/html",
            metadata={"title": title, "filename": path.name},
        )

    def supports(self, source: str | Path) -> bool:
        return str(source).lower().endswith((".html", ".htm"))


class CSVLoader(DocumentLoader):
    async def load(self, source: str | Path) -> LoadedDocument:
        path = Path(source)
        raw = path.read_text(encoding="utf-8")
        reader = csv.DictReader(StringIO(raw))
        rows = list(reader)

        # Represent each row as "key: value" pairs separated by commas
        lines = []
        for row in rows:
            line = ", ".join(f"{k}: {v}" for k, v in row.items() if v is not None)
            lines.append(line)

        return LoadedDocument(
            content="\n".join(lines),
            source_uri=str(path),
            mime_type="text/csv",
            metadata={
                "row_count": len(rows),
                "columns": reader.fieldnames or [],
                "filename": path.name,
            },
        )

    def supports(self, source: str | Path) -> bool:
        return str(source).lower().endswith(".csv")


class JSONLoader(DocumentLoader):
    async def load(self, source: str | Path) -> LoadedDocument:
        path = Path(source)
        data = json.loads(path.read_text(encoding="utf-8"))

        # Pretty-print JSON as readable text for chunking
        content = json.dumps(data, indent=2, ensure_ascii=False)

        return LoadedDocument(
            content=content,
            source_uri=str(path),
            mime_type="application/json",
            metadata={"filename": path.name},
        )

    def supports(self, source: str | Path) -> bool:
        return str(source).lower().endswith(".json")


_LOADERS: list[DocumentLoader] = [
    PDFLoader(),
    DOCXLoader(),
    TextLoader(),
    HTMLLoader(),
    CSVLoader(),
    JSONLoader(),
]


def get_loader(source: str | Path) -> DocumentLoader:
    """Return the first loader that supports the given source."""
    for loader in _LOADERS:
        if loader.supports(source):
            return loader
    raise ValueError(f"No loader available for: {source}")
