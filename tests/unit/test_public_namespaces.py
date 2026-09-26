"""The unauthenticated AI chat must only search the namespaces that are meant to be public."""

from unittest.mock import AsyncMock, MagicMock

import apps.knowledge_platform.api.routes as kp_routes
from aiplatform.quota import register_quota_handler
from aiplatform.retrieval.vector_store import VectorStore
from aiplatform.storage.database import get_session
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_allow_list_is_exactly_the_documented_public_namespaces():
    assert kp_routes.PUBLIC_QUERY_NAMESPACES == ("rag_demo", "skills_hub", "knowledge_platform")
    for private in ("private_hub", "consulting", "corp"):
        assert private not in kp_routes.PUBLIC_QUERY_NAMESPACES


def test_kp_query_route_searches_only_the_allow_list(monkeypatch):
    seen = {}

    class _FakeService:
        def __init__(self, session, app_name=None, **_kwargs):
            seen["app_name"] = app_name

        async def query(self, _request):
            return kp_routes.QueryResponse(
                answer="ok", sources=[], model="m", input_tokens=0, output_tokens=0
            )

    monkeypatch.setattr(kp_routes, "QueryService", _FakeService)
    monkeypatch.setattr(kp_routes, "consume_public_query_quota", AsyncMock())
    app = FastAPI()
    register_quota_handler(app)
    app.include_router(kp_routes.router, prefix="/api/v1")
    app.dependency_overrides[get_session] = lambda: None

    response = TestClient(app).post("/api/v1/kp/query", json={"question": "What is this?"})

    assert response.status_code == 200
    assert seen["app_name"] == list(kp_routes.PUBLIC_QUERY_NAMESPACES)


async def _search_sql_and_params(app_name):
    session = MagicMock()
    result = MagicMock()
    result.mappings.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=result)

    await VectorStore(session).search([0.1, 0.2, 0.3], app_name=app_name)

    statement, params = session.execute.call_args.args
    return str(statement), params


async def test_a_list_becomes_an_any_filter():
    sql, params = await _search_sql_and_params(["rag_demo", "skills_hub"])

    assert "d.app_name = ANY(:app_names)" in sql
    assert params["app_names"] == ["rag_demo", "skills_hub"]


async def test_an_empty_list_still_filters_instead_of_searching_everything():
    sql, params = await _search_sql_and_params([])

    assert "d.app_name = ANY(:app_names)" in sql
    assert params["app_names"] == []


async def test_none_is_the_only_value_that_searches_every_namespace():
    sql, params = await _search_sql_and_params(None)

    assert "app_name" not in sql.split("WHERE", 1)[1]
    assert "app_names" not in params
