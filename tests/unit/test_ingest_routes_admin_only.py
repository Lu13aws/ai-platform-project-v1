"""Write routes of the public API need the admin group, not just any valid token.

The public Cognito pool allows self-registration, and API Gateway's JWT authorizer accepts every
token of that pool. Ingestion writes into the knowledge base the public chat serves, so a plain
signed-in visitor must get 403 (regression: both routes only required a valid token).
"""

from unittest.mock import AsyncMock

import pytest
from aiplatform.storage.database import get_session
from apps.knowledge_platform.api import routes as kp_routes
from apps.rag_demo.api import routes as rag_routes
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROUTES = [
    ("/ingest", {"source_uri": "/tmp/ingest-uploads/a.txt"}),
    ("/kp/ingest-skill", {"title": "t", "content": "some skill content", "source_path": "skills/x.md"}),
]


def _client(groups):
    app = FastAPI()
    app.include_router(rag_routes.router)
    app.include_router(kp_routes.router)

    async def no_db():
        yield None

    app.dependency_overrides[get_session] = no_db

    async def asgi_with_claims(scope, receive, send, _app=app):
        if scope["type"] == "http" and groups is not None:
            claims = {"sub": "u1", "email": "visitor@example.test"}
            if groups:
                claims["cognito:groups"] = "[" + " ".join(groups) + "]"
            scope["aws.event"] = {"requestContext": {"authorizer": {"jwt": {"claims": claims}}}}
        await _app(scope, receive, send)

    return TestClient(asgi_with_claims)


@pytest.fixture(autouse=True)
def _no_real_work(monkeypatch):
    monkeypatch.setattr(rag_routes.IngestService, "ingest", AsyncMock(return_value=rag_routes.IngestResponse(
        document_id="d", chunks_created=1, message="ok")))
    monkeypatch.setattr(kp_routes, "ingest_skill", AsyncMock(return_value=kp_routes.IngestSkillResponse(
        document_id="d", chunks_created=1, skipped=False, message="ok")))


@pytest.mark.parametrize("path, body", ROUTES)
def test_registered_visitor_without_admin_group_is_forbidden(path, body):
    assert _client(groups=[]).post(path, json=body).status_code == 403


@pytest.mark.parametrize("path, body", ROUTES)
def test_other_groups_do_not_grant_access(path, body):
    assert _client(groups=["demo_user"]).post(path, json=body).status_code == 403


@pytest.mark.parametrize("path, body", ROUTES)
def test_request_without_validated_claims_is_unauthorized(path, body):
    assert _client(groups=None).post(path, json=body).status_code == 401


@pytest.mark.parametrize("path, body", ROUTES)
def test_admin_group_is_allowed(path, body):
    assert _client(groups=["corp-admins"]).post(path, json=body).status_code == 200
