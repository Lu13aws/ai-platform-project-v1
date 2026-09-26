import json
import tempfile
from pathlib import Path

import pytest

from aiplatform.ingestion.loaders import (
    CSVLoader,
    HTMLLoader,
    JSONLoader,
    MarkdownLoader,
    TextLoader,
    get_loader,
    validate_source_path,
)
from aiplatform.settings import settings


def write_temp(suffix: str, content: str) -> Path:
    f = tempfile.NamedTemporaryFile(suffix=suffix, mode="w", encoding="utf-8", delete=False)
    f.write(content)
    f.close()
    return Path(f.name)


async def test_text_loader_txt():
    path = write_temp(".txt", "Hello world\nSecond line")
    doc = await TextLoader().load(path)
    assert doc.content == "Hello world\nSecond line"
    assert doc.mime_type == "text/plain"


async def test_markdown_loader_strips_syntax():
    path = write_temp(".md", "# Title\n\nSome **bold** content")
    doc = await MarkdownLoader().load(path)
    assert doc.mime_type == "text/markdown"
    assert doc.content == "Title\n\nSome bold content"


def test_text_loader_leaves_markdown_to_markdown_loader():
    assert not TextLoader().supports("notes.md")
    assert MarkdownLoader().supports("notes.md")


async def test_html_loader_strips_tags():
    html = "<html><head><title>Test</title></head><body><script>var x=1</script><p>Hello</p></body></html>"
    path = write_temp(".html", html)
    doc = await HTMLLoader().load(path)
    assert "Hello" in doc.content
    assert "var x=1" not in doc.content
    assert doc.mime_type == "text/html"
    assert doc.metadata["title"] == "Test"


async def test_csv_loader():
    path = write_temp(".csv", "name,age\nAlice,30\nBob,25")
    doc = await CSVLoader().load(path)
    assert "Alice" in doc.content
    assert "Bob" in doc.content
    assert doc.metadata["row_count"] == 2
    assert doc.mime_type == "text/csv"


async def test_json_loader():
    data = {"project": "ai-platform", "phase": 1}
    path = write_temp(".json", json.dumps(data))
    doc = await JSONLoader().load(path)
    assert "ai-platform" in doc.content
    assert doc.mime_type == "application/json"


def test_get_loader_returns_correct_loader():
    assert type(get_loader("file.pdf")).__name__ == "PDFLoader"
    assert type(get_loader("file.docx")).__name__ == "DOCXLoader"
    assert type(get_loader("file.txt")).__name__ == "TextLoader"
    assert type(get_loader("file.md")).__name__ == "MarkdownLoader"
    assert type(get_loader("file.html")).__name__ == "HTMLLoader"
    assert type(get_loader("file.csv")).__name__ == "CSVLoader"
    assert type(get_loader("file.json")).__name__ == "JSONLoader"


def test_get_loader_raises_for_unknown():
    with pytest.raises(ValueError, match="No loader available"):
        get_loader("file.xyz")


def test_validate_source_path_accepts_path_inside_uploads_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "ingest_uploads_dir", str(tmp_path))
    inside = tmp_path / "doc.txt"
    inside.write_text("hello")

    resolved = validate_source_path(str(inside))

    assert resolved == inside.resolve()


def test_validate_source_path_accepts_the_uploads_dir_itself(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "ingest_uploads_dir", str(tmp_path))
    assert validate_source_path(str(tmp_path)) == tmp_path.resolve()


def test_validate_source_path_rejects_traversal_outside_uploads_dir(monkeypatch, tmp_path):
    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir()
    monkeypatch.setattr(settings, "ingest_uploads_dir", str(uploads_dir))

    outside = uploads_dir / ".." / "secret.txt"

    with pytest.raises(ValueError, match="must be inside"):
        validate_source_path(str(outside))


def test_validate_source_path_rejects_unrelated_absolute_path(monkeypatch, tmp_path):
    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir()
    monkeypatch.setattr(settings, "ingest_uploads_dir", str(uploads_dir))

    with pytest.raises(ValueError, match="must be inside"):
        validate_source_path(str(tmp_path / "other" / "file.py"))
