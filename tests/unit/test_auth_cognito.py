"""
Unit tests for aiplatform.auth.cognito — the shared auth dependency used by
apps/corp_api, apps/knowledge_platform, and apps/rag_demo.

get_current_user only ever reads request.scope["aws.event"] (the claims API
Gateway's JWT authorizer already validated) — it never verifies a token
itself — so these construct that scope directly rather than spinning up a
real API Gateway or a JWT library, matching how the function is actually
exercised in production.
"""

import pytest
from aiplatform.auth.cognito import get_current_user, require_admin
from aiplatform.settings import settings
from fastapi import HTTPException
from starlette.requests import Request


def _request(aws_event: dict | None = None) -> Request:
    scope = {"type": "http", "aws.event": aws_event} if aws_event is not None else {"type": "http"}
    return Request(scope)


async def test_get_current_user_reads_validated_claims_from_api_gateway_event():
    event = {
        "requestContext": {
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": "user-123",
                        "email": "alice@example.com",
                        "cognito:groups": "[corp-admins editors]",
                    }
                }
            }
        }
    }

    user = await get_current_user(_request(event))

    assert user.user_id == "user-123"
    assert user.email == "alice@example.com"
    assert user.groups == ["corp-admins", "editors"]
    assert user.is_admin is True


async def test_get_current_user_rejects_request_with_no_authorizer_claims_and_no_bypass(
    monkeypatch,
):
    monkeypatch.delenv("AUTH_BYPASS", raising=False)

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(_request())

    assert exc_info.value.status_code == 401


async def test_get_current_user_rejects_forged_token_shaped_like_a_jwt(monkeypatch):
    """A hand-crafted bearer token (the pre-fix _require_corp_admin vulnerability)
    carries no aws.event at all — a real API Gateway JWT authorizer never ran,
    so there are no claims to trust, regardless of what the caller sent as an
    Authorization header. This is the exact class of forgery the fix closes."""
    monkeypatch.delenv("AUTH_BYPASS", raising=False)
    scope = {
        "type": "http",
        "headers": [(b"authorization", b"Bearer forged.payload.nosig")],
    }

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(Request(scope))

    assert exc_info.value.status_code == 401


async def test_get_current_user_local_dev_bypass(monkeypatch):
    monkeypatch.setenv("AUTH_BYPASS", "true")

    user = await get_current_user(_request())

    assert user.user_id == "dev-user-local"
    assert user.groups == ["admin"]


async def test_get_current_user_refuses_bypass_in_production(monkeypatch):
    monkeypatch.setenv("AUTH_BYPASS", "true")
    monkeypatch.setattr(settings, "app_env", "production")

    with pytest.raises(RuntimeError, match="refusing to bypass"):
        await get_current_user(_request())


async def test_require_admin_rejects_non_admin_user():
    event = {
        "requestContext": {
            "authorizer": {"jwt": {"claims": {"sub": "u1", "cognito:groups": "[demo_user]"}}}
        }
    }

    with pytest.raises(HTTPException) as exc_info:
        await require_admin(await get_current_user(_request(event)))

    assert exc_info.value.status_code == 403


async def test_require_admin_accepts_corp_admins_group():
    event = {
        "requestContext": {
            "authorizer": {"jwt": {"claims": {"sub": "u1", "cognito:groups": "[corp-admins]"}}}
        }
    }

    user = await require_admin(await get_current_user(_request(event)))

    assert user.is_admin is True
