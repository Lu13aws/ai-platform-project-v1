"""integrity_check: SQL logic (on a portable subset in SQLite) and direct-invoke dispatch."""

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
