"""Tests for the daily public-query quota (aiplatform.quota) and its route wiring."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from aiplatform import quota
from aiplatform.quota import (
    DailyQuotaExceeded,
    _seconds_until_utc_midnight,
    consume_public_query_quota,
    register_quota_handler,
)
from aiplatform.storage.database import get_session
from fastapi import FastAPI
from fastapi.testclient import TestClient


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _NoopContext:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    def __init__(self, row):
        self._row = row
        self.params = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def begin(self):
        return _NoopContext()

    async def execute(self, _stmt, params):
        self.params = params
        return _FakeResult(self._row)


@pytest.fixture
def limit_three(monkeypatch):
    monkeypatch.setattr(quota, "settings", SimpleNamespace(public_daily_llm_limit=3))


def test_seconds_until_utc_midnight():
    assert _seconds_until_utc_midnight(datetime(2026, 9, 26, 23, 59, 30, tzinfo=UTC)) == 30
    assert _seconds_until_utc_midnight(datetime(2026, 9, 27, 0, 0, 0, tzinfo=UTC)) == 86400


async def test_consume_allows_request_while_below_limit(monkeypatch, limit_three):
    session = _FakeSession(row=(1,))
    monkeypatch.setattr(quota, "AsyncSessionLocal", lambda: session)

    await consume_public_query_quota()

    assert session.params["scope"] == "public_query"
    assert session.params["limit"] == 3


async def test_consume_raises_when_limit_reached(monkeypatch, limit_three):
    monkeypatch.setattr(quota, "AsyncSessionLocal", lambda: _FakeSession(row=None))
    notify = AsyncMock()
    monkeypatch.setattr(quota, "_notify_limit_reached_once", notify)

    with pytest.raises(DailyQuotaExceeded) as exc_info:
        await consume_public_query_quota()

    assert exc_info.value.limit == 3
    assert 0 < exc_info.value.retry_after <= 86400
    assert "daily limit of 3" in str(exc_info.value)
    notify.assert_awaited_once()


class _ScriptedSessions:
    """AsyncSessionLocal stand-in: every session pops the next scripted row and logs its SQL."""

    def __init__(self, rows):
        self._rows = list(rows)
        self.statements: list[str] = []

    def __call__(self):
        outer = self

        class _Session(_FakeSession):
            async def execute(self, stmt, params):
                outer.statements.append(str(stmt))
                return _FakeResult(outer._rows.pop(0))

        return _Session(row=None)


_NOW = datetime(2026, 9, 26, 14, 3, tzinfo=UTC)


@pytest.fixture
def sns_topic(monkeypatch):
    monkeypatch.setattr(
        quota, "settings", SimpleNamespace(public_daily_llm_limit=3, sns_topic_arn="arn:aws:sns:test:topic")
    )
    publish = Mock()
    monkeypatch.setattr(quota, "_publish_limit_notice", publish)
    return publish


async def test_notice_sent_once_when_first_to_claim_the_day(monkeypatch, sns_topic):
    monkeypatch.setattr(quota, "AsyncSessionLocal", _ScriptedSessions([(1,)]))

    await quota._notify_limit_reached_once(_NOW, 3)

    sns_topic.assert_called_once_with(3, _NOW)


async def test_notice_not_sent_when_day_already_claimed(monkeypatch, sns_topic):
    monkeypatch.setattr(quota, "AsyncSessionLocal", _ScriptedSessions([None]))

    await quota._notify_limit_reached_once(_NOW, 3)

    sns_topic.assert_not_called()


async def test_failed_publish_releases_claim_and_never_raises(monkeypatch, sns_topic, caplog):
    sessions = _ScriptedSessions([(1,), None])
    monkeypatch.setattr(quota, "AsyncSessionLocal", sessions)
    sns_topic.side_effect = RuntimeError("sns down")

    await quota._notify_limit_reached_once(_NOW, 3)

    assert any("DELETE FROM usage_counters" in s for s in sessions.statements)
    assert "Could not send daily-limit notification" in caplog.text


async def test_missing_topic_skips_publish_and_warns(monkeypatch, sns_topic, caplog):
    monkeypatch.setattr(
        quota, "settings", SimpleNamespace(public_daily_llm_limit=3, sns_topic_arn="")
    )
    monkeypatch.setattr(quota, "AsyncSessionLocal", _ScriptedSessions([(1,)]))

    await quota._notify_limit_reached_once(_NOW, 3)

    sns_topic.assert_not_called()
    assert "SNS_TOPIC_ARN is not set" in caplog.text


def test_handler_returns_429_with_retry_after():
    app = FastAPI()
    register_quota_handler(app)

    @app.get("/boom")
    async def boom():
        raise DailyQuotaExceeded(150, 3600)

    response = TestClient(app).get("/boom")

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "3600"
    assert "150" in response.json()["detail"]


def _app_with(router_module, monkeypatch):
    """Public router with the quota exhausted and QueryService rigged to fail if reached."""
    monkeypatch.setattr(
        router_module, "consume_public_query_quota", AsyncMock(side_effect=DailyQuotaExceeded(150, 60))
    )

    def _must_not_run(*_args, **_kwargs):
        raise AssertionError("QueryService (embedding + LLM) ran although the quota is exhausted")

    monkeypatch.setattr(router_module, "QueryService", _must_not_run)
    app = FastAPI()
    register_quota_handler(app)
    app.include_router(router_module.router, prefix="/api/v1")
    app.dependency_overrides[get_session] = lambda: None
    return TestClient(app)


@pytest.mark.parametrize(
    "module_path, url",
    [
        ("apps.rag_demo.api.routes", "/api/v1/query"),
        ("apps.knowledge_platform.api.routes", "/api/v1/kp/query"),
    ],
)
def test_public_query_routes_stop_before_embedding_when_quota_exhausted(
    module_path, url, monkeypatch
):
    import importlib

    client = _app_with(importlib.import_module(module_path), monkeypatch)

    response = client.post(url, json={"question": "What is this platform?"})

    assert response.status_code == 429
    assert "daily limit" in response.json()["detail"]
