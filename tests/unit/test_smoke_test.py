"""smoke_test: helper logic, and that every Lambda handler answers it without running its pipeline."""

import importlib
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiplatform import smoke
from fastapi import FastAPI

HANDLERS = [
    ("apps.cleanup.lambda_handler", "cleanup"),
    ("apps.competitor_pipeline.lambda_handler", "competitor-pipeline"),
    ("apps.content_creator.lambda_handler", "content-creator"),
    ("apps.corp_api.lambda_handler", "corp-api"),
    ("apps.radar_pipeline.lambda_handler", "radar-pipeline"),
    ("apps.rag_demo.lambda_handler", "rag-demo"),
    ("apps.regulatory_pipeline.lambda_handler", "regulatory-pipeline"),
    ("apps.token_price_pipeline.lambda_handler", "token-price-pipeline"),
]


@pytest.mark.parametrize(
    "event",
    [
        None,
        {},
        {"version": "2.0", "routeKey": "GET /health"},  # API Gateway
        {"source": "aws.events", "detail-type": "Scheduled Event"},  # EventBridge
        {"action": "run_migrations"},
    ],
)
def test_other_events_are_left_to_the_handler(event):
    assert smoke.handle_smoke_test(event, "x") is None


def test_smoke_test_reports_ok_when_the_database_answers(monkeypatch):
    monkeypatch.setattr(smoke, "_ping", AsyncMock())

    result = smoke.handle_smoke_test({"action": "smoke_test"}, "radar-pipeline", lambda: object())

    assert result["status"] == "ok"
    assert result["function"] == "radar-pipeline"
    assert result["database"] == "ok"


def test_smoke_test_reports_the_error_instead_of_raising(monkeypatch):
    monkeypatch.setattr(smoke, "_ping", AsyncMock(side_effect=ConnectionRefusedError("db down")))

    result = smoke.handle_smoke_test({"action": "smoke_test"}, "cleanup", lambda: object())

    assert result["status"] == "error"
    assert result["database"].startswith("ConnectionRefusedError")


@pytest.mark.parametrize("module_path, expected_name", HANDLERS)
def test_every_handler_answers_the_smoke_test_without_running_its_pipeline(
    module_path, expected_name, monkeypatch
):
    if module_path == "apps.rag_demo.lambda_handler":
        # The real apps.rag_demo.main opens a DB connection at import time.
        monkeypatch.setitem(sys.modules, "apps.rag_demo.main", SimpleNamespace(app=FastAPI()))
        sys.modules.pop(module_path, None)
    module = importlib.import_module(module_path)
    monkeypatch.setattr(smoke, "_ping", AsyncMock())

    result = module.handler({"action": "smoke_test"}, None)

    assert result["status"] == "ok"
    assert result["function"] == expected_name
    if module_path == "apps.rag_demo.lambda_handler":
        sys.modules.pop(module_path, None)


def test_direct_invoke_engine_is_unpooled_and_separate_from_the_shared_engine():
    """A pooled connection from an earlier HTTP request lives in another event loop and breaks the
    asyncio.run() of a direct-invoke action ("attached to a different loop")."""
    from aiplatform.storage.database import create_oneshot_engine, engine

    oneshot = create_oneshot_engine()

    assert oneshot.pool.__class__.__name__ == "NullPool"
    assert oneshot is not engine
    assert oneshot.url == engine.url
