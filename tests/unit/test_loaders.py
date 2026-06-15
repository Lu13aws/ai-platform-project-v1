import json
import tempfile
from pathlib import Path

import pytest

from aiplatform.ingestion.loaders import (
    CSVLoader,
    HTMLLoader,
    JSONLoader,
    TextLoader,
    get_loader,
)


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


async def test_text_loader_md():
    path = write_temp(".md", "# Title\n\nSome content")
    doc = await TextLoader().load(path)
    assert doc.mime_type == "text/markdown"
    assert "Title" in doc.content


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
    assert type(get_loader("file.md")).__name__ == "TextLoader"
    assert type(get_loader("file.html")).__name__ == "HTMLLoader"
    assert type(get_loader("file.csv")).__name__ == "CSVLoader"
    assert type(get_loader("file.json")).__name__ == "JSONLoader"


def test_get_loader_raises_for_unknown():
    with pytest.raises(ValueError, match="No loader available"):
        get_loader("file.xyz")
