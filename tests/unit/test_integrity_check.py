"""integrity_check: SQL logic (on a portable subset in SQLite) and direct-invoke dispatch."""

import asyncio
import importlib
import sqlite3
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from aiplatform.storage.integrity import PER_APP_SQL, TOTALS_SQL
from fastapi import FastAPI


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE documents  (id INTEGER PRIMARY KEY, app_name TEXT);
        CREATE TABLE chunks     (id INTEGER PRIMARY KEY, document_id INTEGER);
        CREATE TABLE embeddings (id INTEGER PRIMARY KEY, chunk_id INTEGER);
        INSERT INTO documents VALUES (1, 'rag_demo'), (2, 'rag_demo'), (3, 'skills_hub'), (4, 'skills_hub');
        -- doc 1: 3 chunks, the last one has no vector (what zip() truncation used to cause)
        INSERT INTO chunks VALUES (1, 1), (2, 1), (3, 1);
        INSERT INTO embeddings VALUES (1, 1), (2, 2);
        -- doc 2: 2 chunks, both embedded; doc 3: 1 chunk, embedded; doc 4: no chunks at all
        INSERT INTO chunks VALUES (4, 2), (5, 2), (6, 3);
        INSERT INTO embeddings VALUES (3, 4), (4, 5), (5, 6);
        """
    )
    yield conn
    conn.close()


def test_totals_count_missing_embeddings_and_empty_documents(db):
    cur = db.execute(TOTALS_SQL)
    row = dict(zip([c[0] for c in cur.description], cur.fetchone(), strict=True))

    assert row == {
        "documents_total": 4,
        "chunks_total": 6,
        "chunks_without_embedding": 1,
        "documents_without_chunks": 1,
    }


def test_per_app_breakdown(db):
    cur = db.execute(PER_APP_SQL)
    cols = [c[0] for c in cur.description]
    rows = [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]

    assert rows == [
        {"app_name": "rag_demo", "documents": 2, "chunks": 5, "chunks_without_embedding": 1},
        {"app_name": "skills_hub", "documents": 2, "chunks": 1, "chunks_without_embedding": 0},
    ]


@pytest.fixture
def lambda_handler(monkeypatch):
    # The real apps.rag_demo.main opens a DB connection at import time.
    monkeypatch.setitem(sys.modules, "apps.rag_demo.main", SimpleNamespace(app=FastAPI()))
    sys.modules.pop("apps.rag_demo.lambda_handler", None)
    module = importlib.import_module("apps.rag_demo.lambda_handler")
    yield module
    sys.modules.pop("apps.rag_demo.lambda_handler", None)


def test_direct_invoke_action_returns_the_counts(lambda_handler, monkeypatch):
    counts = {"totals": {"chunks_without_embedding": 0}, "per_app": []}
    monkeypatch.setattr(lambda_handler, "_integrity_check", AsyncMock(return_value=counts))

    result = lambda_handler.handler({"action": "integrity_check"}, None)

    assert result == {"status": "ok", **counts}


def test_http_events_never_reach_the_integrity_check(lambda_handler, monkeypatch):
    check = AsyncMock()
    monkeypatch.setattr(lambda_handler, "_integrity_check", check)
    monkeypatch.setattr(lambda_handler, "_mangum", Mock(return_value={"statusCode": 200}))
    http_event = {"version": "2.0", "routeKey": "POST /api/v1/query", "rawPath": "/api/v1/query"}

    assert lambda_handler.handler(http_event, None) == {"statusCode": 200}
    check.assert_not_called()


@pytest.mark.parametrize(
    "action, coroutine_name, result",
    [
        ("integrity_check", "_integrity_check", {"totals": {}, "per_app": []}),
        ("run_migrations", "_run_migrations", ["applied"]),
    ],
)
def test_direct_invoke_actions_leave_a_usable_event_loop(
    lambda_handler, monkeypatch, action, coroutine_name, result
):
    """asyncio.run() closes the loop; Mangum needs a current one again on the next HTTP request
    served by the same warm container (regression: every request returned 500)."""
    monkeypatch.setattr(lambda_handler, coroutine_name, AsyncMock(return_value=result))

    lambda_handler.handler({"action": action}, None)

    asyncio.get_event_loop_policy().get_event_loop()  # raised RuntimeError before the fix


def test_http_request_is_still_served_after_a_direct_invoke_action(lambda_handler, monkeypatch):
    """The production sequence that returned 500: a direct-invoke action, then an HTTP request
    handled by the same warm container through the real Mangum adapter."""
    from mangum import Mangum

    app = FastAPI()

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    monkeypatch.setattr(lambda_handler, "_mangum", Mangum(app, lifespan="off"))
    monkeypatch.setattr(
        lambda_handler, "_integrity_check", AsyncMock(return_value={"totals": {}, "per_app": []})
    )
    http_event = {
        "version": "2.0",
        "routeKey": "GET /health",
        "rawPath": "/health",
        "rawQueryString": "",
        "headers": {"host": "example.test"},
        "requestContext": {
            "http": {"method": "GET", "path": "/health", "protocol": "HTTP/1.1", "sourceIp": "127.0.0.1"},
            "stage": "$default",
        },
        "isBase64Encoded": False,
    }

    lambda_handler.handler({"action": "integrity_check"}, None)
    response = lambda_handler.handler(http_event, None)

    assert response["statusCode"] == 200


def test_document_metadata_query_lists_one_namespace_without_content():
    from aiplatform.storage.integrity import DOCUMENTS_SQL

    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE documents (id INTEGER PRIMARY KEY, title TEXT, source_uri TEXT, mime_type TEXT,
                                created_at TEXT, app_name TEXT, content_hash TEXT);
        CREATE TABLE chunks (id INTEGER PRIMARY KEY, document_id INTEGER, content TEXT);
        INSERT INTO documents VALUES (1, 'A', 'notes/a.md', 'text/markdown', '2026-01-02', 'private_hub', 'h1');
        INSERT INTO documents VALUES (2, 'B', 'notes/b.md', 'text/markdown', '2026-01-01', 'private_hub', 'h2');
        INSERT INTO documents VALUES (3, 'C', 'skills/c.md', 'text/markdown', '2026-01-03', 'skills_hub', 'h3');
        INSERT INTO chunks VALUES (1, 1, 'secret body'), (2, 1, 'secret body 2'), (3, 2, 'more');
        """
    )
    cur = conn.execute(DOCUMENTS_SQL, {"app_name": "private_hub"})
    cols = [c[0] for c in cur.description]
    rows = [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]

    assert [r["source_uri"] for r in rows] == ["notes/b.md", "notes/a.md"]  # oldest first
    assert [r["chunks"] for r in rows] == [1, 2]
    assert "content" not in cols and "content_hash" not in cols


def test_list_documents_action_returns_the_metadata(lambda_handler, monkeypatch):
    docs = [{"title": "A", "source_uri": "notes/a.md", "chunks": 2}]
    listing = AsyncMock(return_value=docs)
    monkeypatch.setattr(lambda_handler, "_list_documents", listing)

    result = lambda_handler.handler({"action": "list_documents", "app_name": "private_hub"}, None)

    assert result == {"status": "ok", "app_name": "private_hub", "count": 1, "documents": docs}
    listing.assert_awaited_once_with("private_hub")
    asyncio.get_event_loop_policy().get_event_loop()  # loop is usable again for the next HTTP request


def test_list_documents_action_requires_an_app_name(lambda_handler, monkeypatch):
    listing = AsyncMock()
    monkeypatch.setattr(lambda_handler, "_list_documents", listing)

    result = lambda_handler.handler({"action": "list_documents"}, None)

    assert result["status"] == "error"
    listing.assert_not_called()
