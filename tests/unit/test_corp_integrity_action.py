"""corp-api direct-invoke integrity_check: dispatch only (the SQL is shared with the public check)."""

import asyncio
import importlib
import sys
from unittest.mock import AsyncMock, Mock

import pytest


@pytest.fixture
def corp_handler():
    sys.modules.pop("apps.corp_api.lambda_handler", None)
    module = importlib.import_module("apps.corp_api.lambda_handler")
    yield module
    sys.modules.pop("apps.corp_api.lambda_handler", None)


def test_direct_invoke_returns_the_counts_and_leaves_a_usable_loop(corp_handler, monkeypatch):
    counts = {"totals": {"documents_total": 3}, "per_app": [], "audit_logs": 12}
    monkeypatch.setattr(corp_handler, "_integrity_check", AsyncMock(return_value=counts))

    result = corp_handler.handler({"action": "integrity_check"}, None)

    assert result == {"status": "ok", **counts}
    asyncio.get_event_loop_policy().get_event_loop()  # the warm Mangum loop must survive the action


def test_http_events_never_reach_the_integrity_check(corp_handler, monkeypatch):
    check = AsyncMock()
    monkeypatch.setattr(corp_handler, "_integrity_check", check)
    monkeypatch.setattr(corp_handler, "_mangum", Mock(return_value={"statusCode": 200}))

    http_event = {"version": "2.0", "routeKey": "GET /api/v1/corp/health", "rawPath": "/api/v1/corp/health"}

    assert corp_handler.handler(http_event, None) == {"statusCode": 200}
    check.assert_not_called()
