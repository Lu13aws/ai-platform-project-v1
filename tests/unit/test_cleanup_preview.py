"""Cleanup: the read-only preview must use exactly the conditions the real run deletes with."""

import asyncio
import importlib
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiplatform.agents.cleanup import CleanupAgent, _conditions
from sqlalchemy import delete, select
from sqlalchemy.dialects import postgresql


def _sql(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": False}))


def test_every_retention_category_has_a_condition():
    assert set(_conditions()) == {
        "raw_articles",
        "radar_reports",
        "regulatory_reports",
        "competitor_raw_content",
        "competitor_signals",
        "competitor_reports",
        "linkedin_posts",
    }


def test_regulatory_documents_and_changes_are_never_candidates():
    assert "regulatory_documents" not in _conditions()
    assert "regulatory_changes" not in _conditions()


def test_preview_counts_with_the_same_where_clause_as_the_delete():
    seen = []

    class Session:
        async def execute(self, stmt):
            seen.append(("execute", str(stmt)))

        async def scalar(self, stmt):
            seen.append(("scalar", _sql(stmt)))
            return 7

    result = asyncio.run(CleanupAgent(s3=MagicMock()).preview(Session()))

    assert seen[0] == ("execute", "SET TRANSACTION READ ONLY")
    for name, (model, condition) in _conditions().items():
        assert result[name] == {"would_delete": 7, "total": 7}
        delete_where = _sql(delete(model).where(condition)).split(" WHERE ", 1)[1]
        count_sql = _sql(select(model).where(condition))
        assert delete_where in count_sql, name


@pytest.fixture
def cleanup_handler(monkeypatch):
    sys.modules.pop("apps.cleanup.lambda_handler", None)
    module = importlib.import_module("apps.cleanup.lambda_handler")
    yield module
    sys.modules.pop("apps.cleanup.lambda_handler", None)


def test_preview_action_never_runs_the_cleanup(cleanup_handler, monkeypatch):
    counts = {"raw_articles": {"would_delete": 1, "total": 2}}
    monkeypatch.setattr(cleanup_handler, "_preview", AsyncMock(return_value=counts))
    run = AsyncMock()
    monkeypatch.setattr(cleanup_handler, "_run_cleanup", run)

    result = cleanup_handler.handler({"action": "preview"}, None)

    assert result == {"status": "ok", "would_delete": counts}
    run.assert_not_called()


def test_scheduled_event_still_runs_the_real_cleanup(cleanup_handler, monkeypatch):
    preview = AsyncMock()
    monkeypatch.setattr(cleanup_handler, "_preview", preview)
    monkeypatch.setattr(cleanup_handler, "_run_cleanup", AsyncMock(return_value={"articles_deleted": 0}))

    result = cleanup_handler.handler({"source": "aws.events"}, None)

    assert result["statusCode"] == 200
    preview.assert_not_called()
