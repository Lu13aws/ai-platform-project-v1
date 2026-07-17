"""
Route-wiring guard: confirms the auth dependency is actually attached to
each route that needs one, by inspecting FastAPI's own dependency graph —
not by calling the routes through a TestClient (this repo has no TestClient
harness yet, and building one is out of scope for this fix). This is the
one thing worth locking down: it's exactly the class of regression this
whole fix exists to close (a route silently losing its auth dependency).
"""

from apps.knowledge_platform.api.routes import router as kp_router
from apps.rag_demo.api.routes import router as rag_demo_router


def _dependency_names(route) -> set[str]:
    return {dep.call.__name__ for dep in route.dependant.dependencies}


def _route(router, method: str, path: str):
    for r in router.routes:
        if method in r.methods and r.path == path:
            return r
    raise AssertionError(f"no route found for {method} {path}")


def test_knowledge_platform_query_requires_admin():
    assert "require_admin" in _dependency_names(_route(kp_router, "POST", "/kp/query"))


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
