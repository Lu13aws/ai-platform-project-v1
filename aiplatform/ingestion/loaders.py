"""
Concrete document loaders for PDF, DOCX, TXT, Markdown, HTML, CSV, JSON,
Excel (.xlsx), and source code files (.py, .ts, .js, .sql, .yaml, .toml, .sh).
"""

import csv
import json
import re
from io import StringIO
from pathlib import Path

from aiplatform.ingestion.base import DocumentLoader, LoadedDocument


class PDFLoader(DocumentLoader):
    async def load(self, source: str | Path) -> LoadedDocument:
        import pdfplumber

        path = Path(source)
        pages = []
        with pdfplumber.open(str(path)) as pdf:
            page_count = len(pdf.pages)
            for page in pdf.pages:
                text = page.extract_text(x_tolerance=2, y_tolerance=3) or ""
                if text.strip():
                    pages.append(text)

        return LoadedDocument(
            content="\n\n".join(pages),
            source_uri=str(path),
            mime_type="application/pdf",
            metadata={
                "page_count": page_count,
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


def _strip_markdown(text: str) -> str:
    """Remove markdown syntax, preserving all meaningful content for embedding."""
    # Fenced code blocks — remove fences, keep code content
    text = re.sub(r'```[^\n]*\n([\s\S]*?)```', r'\1', text)
    text = re.sub(r'~~~[^\n]*\n([\s\S]*?)~~~', r'\1', text)
    # Inline code — keep content
    text = re.sub(r'`([^`\n]+)`', r'\1', text)
    # Headers — remove # markers, keep text
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # Bold / italic / strikethrough — keep inner text
    text = re.sub(r'\*{3}([^*\n]+)\*{3}', r'\1', text)
    text = re.sub(r'\*{2}([^*\n]+)\*{2}', r'\1', text)
    text = re.sub(r'\*([^*\n]+)\*', r'\1', text)
    text = re.sub(r'_{3}([^_\n]+)_{3}', r'\1', text)
    text = re.sub(r'_{2}([^_\n]+)_{2}', r'\1', text)
    text = re.sub(r'_([^_\n]+)_', r'\1', text)
    text = re.sub(r'~~([^~\n]+)~~', r'\1', text)
    # Images — remove (alt text is rarely useful for search)
    text = re.sub(r'!\[[^\]]*\]\([^\)]*\)', '', text)
    # Links — keep link text, drop URL
    text = re.sub(r'\[([^\]]+)\]\([^\)]*\)', r'\1', text)
    text = re.sub(r'\[([^\]]+)\]\[[^\]]*\]', r'\1', text)
    # HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Table separator rows (|---|---| or |:---|---:|)
    text = re.sub(r'^\|[-:| ]+\|$', '', text, flags=re.MULTILINE)
    # Table pipes — replace with two spaces so cells stay readable
    text = re.sub(r'\s*\|\s*', '  ', text)
    # Horizontal rules
    text = re.sub(r'^[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)
    # Blockquotes
    text = re.sub(r'^>\s?', '', text, flags=re.MULTILINE)
    # Unordered list markers (-, *, +)
    text = re.sub(r'^(\s*)[-*+]\s+', r'\1', text, flags=re.MULTILINE)
    # Ordered list markers (1. or 1))
    text = re.sub(r'^(\s*)\d+[.)]\s+', r'\1', text, flags=re.MULTILINE)
    # Collapse runs of blank lines and trailing spaces
    text = re.sub(r' {3,}', '  ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


class MarkdownLoader(DocumentLoader):
    """Handles .md files — strips markdown syntax before embedding for better similarity scores."""

    async def load(self, source: str | Path) -> LoadedDocument:
        path = Path(source)
        raw = path.read_text(encoding="utf-8", errors="replace")
        content = _strip_markdown(raw)
        return LoadedDocument(
            content=content,
            source_uri=str(path),
            mime_type="text/markdown",
            metadata={"filename": path.name, "raw_length": len(raw)},
        )

    def supports(self, source: str | Path) -> bool:
        return Path(source).suffix.lower() == ".md"


class TextLoader(DocumentLoader):
    """Handles plain .txt files."""

    async def load(self, source: str | Path) -> LoadedDocument:
        path = Path(source)
        content = path.read_text(encoding="utf-8")

        return LoadedDocument(
            content=content,
            source_uri=str(path),
            mime_type="text/plain",
            metadata={"filename": path.name},
        )

    def supports(self, source: str | Path) -> bool:
        return str(source).lower().endswith(".txt")


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


_CODE_LANGUAGE_MAP: dict[str, str] = {
    ".py":   "python",
    ".ts":   "typescript",
    ".js":   "javascript",
    ".sql":  "sql",
    ".yaml": "yaml",
    ".yml":  "yaml",
    ".toml": "toml",
    ".sh":   "bash",
    ".tf":   "terraform",
}


class CodeFileLoader(DocumentLoader):
    """Handles source code and config files (.py, .ts, .js, .sql, .yaml, .toml, .sh, .tf)."""

    _EXTENSIONS = frozenset(_CODE_LANGUAGE_MAP.keys())

    async def load(self, source: str | Path) -> LoadedDocument:
        path = Path(source)
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = path.read_text(encoding="latin-1")

        language = _CODE_LANGUAGE_MAP.get(path.suffix.lower(), "text")

        return LoadedDocument(
            content=content,
            source_uri=str(path),
            mime_type="text/plain",
            metadata={
                "filename": path.name,
                "language": language,
                "line_count": len(content.splitlines()),
            },
        )

    def supports(self, source: str | Path) -> bool:
        return Path(source).suffix.lower() in self._EXTENSIONS


class ExcelLoader(DocumentLoader):
    """Handles .xlsx files — converts each sheet to pipe-delimited text rows."""

    async def load(self, source: str | Path) -> LoadedDocument:
        import openpyxl

        path = Path(source)
        wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)

        sheets_text: list[str] = []
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            rows: list[str] = []
            for row in ws.iter_rows(values_only=True):
                cells = [str(c) if c is not None else "" for c in row]
                if any(c.strip() for c in cells):
                    rows.append(" | ".join(cells))
            if rows:
                sheets_text.append(f"Sheet: {sheet_name}\n" + "\n".join(rows))

        wb.close()

        return LoadedDocument(
            content="\n\n".join(sheets_text),
            source_uri=str(path),
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            metadata={
                "filename": path.name,
                "sheet_count": len(sheets_text),
            },
        )

    def supports(self, source: str | Path) -> bool:
        return str(source).lower().endswith(".xlsx")


_LOADERS: list[DocumentLoader] = [
    PDFLoader(),
    DOCXLoader(),
    MarkdownLoader(),
    TextLoader(),
    HTMLLoader(),
    CSVLoader(),
    JSONLoader(),
    ExcelLoader(),
    CodeFileLoader(),
]


def get_loader(source: str | Path) -> DocumentLoader:
    """Return the first loader that supports the given source."""
    for loader in _LOADERS:
        if loader.supports(source):
            return loader
    raise ValueError(f"No loader available for: {source}")


SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({
    ".pdf", ".docx", ".txt", ".md",
    ".html", ".htm", ".csv", ".json", ".xlsx",
    *_CODE_LANGUAGE_MAP.keys(),
})
