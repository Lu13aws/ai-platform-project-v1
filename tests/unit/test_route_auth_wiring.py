"""
Route-wiring guard: confirms the auth dependency is actually attached to
each route that needs one, by inspecting FastAPI's own dependency graph —
not by calling the routes through a TestClient (this repo has no TestClient
harness yet, and building one is out of scope for this fix). This is the
one thing worth locking down: it's exactly the class of regression this
whole fix exists to close (a route silently losing its auth dependency).

One exception: the public query routes are protected by the daily LLM quota,
which lives in the handler and not in the dependency graph, so their test also
sends an (unauthenticated) request through a TestClient.
"""

from unittest.mock import AsyncMock

import apps.knowledge_platform.api.routes as kp_routes
from aiplatform.quota import DailyQuotaExceeded, register_quota_handler
from aiplatform.storage.database import get_session
from apps.knowledge_platform.api.routes import router as kp_router
from apps.rag_demo.api.routes import router as rag_demo_router
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _dependency_names(route) -> set[str]:
    return {dep.call.__name__ for dep in route.dependant.dependencies}


def _route(router, method: str, path: str):
    for r in router.routes:
        if method in r.methods and r.path == path:
            return r
    raise AssertionError(f"no route found for {method} {path}")


def test_knowledge_platform_query_is_public_but_daily_quota_limited(monkeypatch):
    """/kp/query is a deliberately public portfolio feature (the AI Chat on
    platform.bridging-data.com sends no Authorization header). It is protected
    by the daily LLM quota instead of by authentication."""
    route = _route(kp_router, "POST", "/kp/query")
    assert not {"require_admin", "get_current_user"} & _dependency_names(route)

    # Unauthenticated request, quota exhausted: 429 (quota), not 401/403 (auth).
    monkeypatch.setattr(
        kp_routes, "consume_public_query_quota", AsyncMock(side_effect=DailyQuotaExceeded(150, 60))
    )
    app = FastAPI()
    register_quota_handler(app)
    app.include_router(kp_router, prefix="/api/v1")
    app.dependency_overrides[get_session] = lambda: None

    response = TestClient(app).post("/api/v1/kp/query", json={"question": "What is this platform?"})

    assert response.status_code == 429


def test_rag_demo_query_is_public():
    route = _route(rag_demo_router, "POST", "/query")
    assert not {"require_admin", "get_current_user"} & _dependency_names(route)


def test_knowledge_platform_ingest_skill_requires_authentication():
    assert "get_current_user" in _dependency_names(
        _route(kp_router, "POST", "/kp/ingest-skill")
    )


def test_knowledge_platform_linkedin_routes_require_admin():
    linkedin_routes = [
        ("GET", "/kp/linkedin"),
        ("PATCH", "/kp/linkedin/{post_id}"),
        ("POST", "/kp/linkedin/{post_id}/regenerate"),
        ("POST", "/kp/linkedin/{post_id}/publish"),
        ("DELETE", "/kp/linkedin/{post_id}"),
    ]
    for method, path in linkedin_routes:
        assert "require_admin" in _dependency_names(_route(kp_router, method, path)), (
            f"{method} {path} is missing the require_admin dependency"
        )


def test_rag_demo_ingest_requires_authentication():
    assert "get_current_user" in _dependency_names(_route(rag_demo_router, "POST", "/ingest"))
