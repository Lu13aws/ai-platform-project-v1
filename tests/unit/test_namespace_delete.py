"""delete_namespace: guards, transaction behaviour (SQLite with cascading FKs) and dispatch."""

import asyncio
import importlib
import sqlite3
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiplatform.storage.namespace_delete import (
    NamespaceDeleteRefused,
    confirmation_for,
    delete_namespace,
    validate_request,
)
from fastapi import FastAPI


class _Rows:
    def __init__(self, cursor):
        cols = [c[0] for c in cursor.description or []]  # a DELETE has no result columns
        self._rows = [dict(zip(cols, r, strict=True)) for r in cursor.fetchall()]

    def mappings(self):
        return self

    def one(self):
        assert len(self._rows) == 1
        return self._rows[0]


class _Trans:
    def __init__(self, db):
        self._db = db

    async def commit(self):
        self._db.commit()

    async def rollback(self):
        self._db.rollback()


class _Conn:
    def __init__(self, db):
        self._db = db

    async def begin(self):
        return _Trans(self._db)

    async def execute(self, clause, params=None):
        return _Rows(self._db.execute(str(clause), params or {}))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeEngine:
    """Just enough of AsyncEngine for delete_namespace, backed by a real SQLite database."""

    def __init__(self, db):
        self.db = db

    def connect(self):
        return _Conn(self.db)


@pytest.fixture
def engine():
    db = sqlite3.connect(":memory:", isolation_level=None)
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript(
        """
        CREATE TABLE documents  (id INTEGER PRIMARY KEY, app_name TEXT);
        CREATE TABLE chunks     (id INTEGER PRIMARY KEY,
                                 document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE);
        CREATE TABLE embeddings (id INTEGER PRIMARY KEY,
                                 chunk_id INTEGER REFERENCES chunks(id) ON DELETE CASCADE);
        INSERT INTO documents VALUES (1, 'private_hub'), (2, 'private_hub'), (3, 'skills_hub');
        INSERT INTO chunks VALUES (1, 1), (2, 1), (3, 2), (4, 3);
        INSERT INTO embeddings VALUES (1, 1), (2, 2), (3, 3), (4, 4);
        """
    )
    # sqlite3 autocommit mode: emulate the explicit transaction the code opens with conn.begin()
    original_begin = _Conn.begin

    async def begin(self):
        self._db.execute("BEGIN")
        return await original_begin(self)

    _Conn.begin = begin
    yield FakeEngine(db)
    _Conn.begin = original_begin
    db.close()


def _counts(engine):
    q = engine.db.execute
    return (
        q("SELECT COUNT(*) FROM documents WHERE app_name = 'private_hub'").fetchone()[0],
        q("SELECT COUNT(*) FROM documents").fetchone()[0],
        q("SELECT COUNT(*) FROM chunks").fetchone()[0],
        q("SELECT COUNT(*) FROM embeddings").fetchone()[0],
    )


CONFIRM = "DELETE-PRIVATE-HUB-2"


def test_confirmation_string_is_derived_from_namespace_and_count():
    assert confirmation_for("private_hub", 68) == "DELETE-PRIVATE-HUB-68"


@pytest.mark.parametrize(
    "app_name, expected, confirm",
    [
        ("", 2, CONFIRM),
        (None, 2, CONFIRM),
        ("rag_demo", 2, "DELETE-RAG-DEMO-2"),  # public namespace, even with a correct confirmation
        ("skills_hub", 2, "DELETE-SKILLS-HUB-2"),
        ("knowledge_platform", 2, "DELETE-KNOWLEDGE-PLATFORM-2"),
        ("private_hub", 0, "DELETE-PRIVATE-HUB-0"),
        ("private_hub", True, "DELETE-PRIVATE-HUB-True"),
        ("private_hub", "2", CONFIRM),
        ("private_hub", 2, None),
        ("private_hub", 2, "delete-private-hub-2"),
        ("private_hub", 2, "DELETE-PRIVATE-HUB-68"),  # confirmation for another count
    ],
)
def test_guards_refuse_unsafe_requests(app_name, expected, confirm):
    with pytest.raises(NamespaceDeleteRefused):
        validate_request(app_name, expected, confirm)


def test_dry_run_deletes_inside_the_transaction_and_rolls_back(engine):
    result = asyncio.run(delete_namespace(engine, "private_hub", 2, CONFIRM, dry_run=True))

    assert result["committed"] is False
    assert result["deleted"] == {"documents": 2, "chunks": 3, "embeddings": 3}
    assert result["remaining"] == {"documents": 0, "chunks": 0, "embeddings": 0}
    assert _counts(engine) == (2, 3, 4, 4)  # untouched


def test_real_run_removes_only_that_namespace_and_leaves_no_orphans(engine):
    result = asyncio.run(delete_namespace(engine, "private_hub", 2, CONFIRM, dry_run=False))

    assert result["committed"] is True
    assert result["orphans"] == {"orphan_chunks": 0, "orphan_embeddings": 0}
    assert _counts(engine) == (0, 1, 1, 1)  # the skills_hub document, its chunk and embedding remain


def test_count_mismatch_deletes_nothing(engine):
    engine.db.execute("INSERT INTO documents VALUES (9, 'private_hub')")  # 3 documents now, 2 expected

    with pytest.raises(NamespaceDeleteRefused, match="found 3 documents, expected 2"):
        asyncio.run(delete_namespace(engine, "private_hub", 2, CONFIRM, dry_run=False))

    assert _counts(engine) == (3, 4, 4, 4)


@pytest.fixture
def lambda_handler(monkeypatch):
    monkeypatch.setitem(sys.modules, "apps.rag_demo.main", SimpleNamespace(app=FastAPI()))
    sys.modules.pop("apps.rag_demo.lambda_handler", None)
    module = importlib.import_module("apps.rag_demo.lambda_handler")
    yield module
    sys.modules.pop("apps.rag_demo.lambda_handler", None)


def test_action_defaults_to_a_dry_run(lambda_handler, monkeypatch):
    delete = AsyncMock(return_value={"dry_run": True, "committed": False})
    monkeypatch.setattr(lambda_handler, "_delete_namespace", delete)
    event = {"action": "delete_namespace", "app_name": "private_hub", "expected_documents": 2, "confirm": CONFIRM}

    lambda_handler.handler(event, None)

    delete.assert_awaited_once_with("private_hub", 2, CONFIRM, True)
    asyncio.get_event_loop_policy().get_event_loop()  # loop usable again for the next HTTP request


@pytest.mark.parametrize("dry_run", ["false", 0, None, "no"])
def test_only_an_explicit_false_turns_the_dry_run_off(lambda_handler, monkeypatch, dry_run):
    delete = AsyncMock(return_value={})
    monkeypatch.setattr(lambda_handler, "_delete_namespace", delete)
    event = {"action": "delete_namespace", "app_name": "x", "expected_documents": 1, "confirm": "c", "dry_run": dry_run}

    lambda_handler.handler(event, None)

    assert delete.await_args.args[3] is True

    event["dry_run"] = False
    lambda_handler.handler(event, None)
    assert delete.await_args.args[3] is False


def test_refusal_is_reported_not_raised(lambda_handler, monkeypatch):
    monkeypatch.setattr(lambda_handler, "_delete_namespace", AsyncMock(side_effect=NamespaceDeleteRefused("nope")))

    result = lambda_handler.handler({"action": "delete_namespace", "app_name": "rag_demo"}, None)

    assert result == {"status": "refused", "error": "nope"}
