"""
Cognito JWT authentication — shared across every app behind an API Gateway
HTTP API with a Cognito JWT authorizer attached.

Production (Lambda + API Gateway):
  API Gateway's JWT Authorizer validates the token's signature/issuer/audience
  BEFORE the Lambda is ever invoked — this module never verifies a token
  itself, it only reads the already-validated claims API Gateway attaches to
  the Lambda-proxy event. That means the security boundary is the per-route
  AuthorizationType="JWT" + AuthorizerId configuration in the relevant deploy
  script (see scripts/deploy_corp_api.py and scripts/deploy_lambda.py) — a
  route with no authorizer attached gets no claims here and falls straight
  through to a 401 (or the AUTH_BYPASS escape hatch below).

Local development:
  Set AUTH_BYPASS=true to skip auth (admin identity assumed).

This module is intentionally pool-agnostic: it doesn't hardcode a Cognito
User Pool ID or issuer anywhere, so the same code serves every app even
though apps/corp_api and apps/knowledge_platform/apps/rag_demo authenticate
against two different Cognito User Pools — the pool is only ever selected by
which authorizer API Gateway attached to the route that was hit.
"""

import os
from dataclasses import dataclass, field

from fastapi import Depends, HTTPException, Request, status


@dataclass
class UserClaims:
    user_id: str
    email: str
    groups: list[str] = field(default_factory=list)

    @property
    def is_admin(self) -> bool:
        return "corp-admins" in self.groups

    @property
    def is_demo_user(self) -> bool:
        return "corp-admins" in self.groups


def _parse_groups(raw: str | list | None) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    # API Gateway serializes Cognito group arrays as "[group1 group2]" (with brackets)
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    return [g.strip() for g in raw.split() if g.strip()]


async def get_current_user(request: Request) -> UserClaims:
    # Production: API Gateway JWT Authorizer injects validated claims into event context
    apigw_event = request.scope.get("aws.event", {})
    if apigw_event:
        claims = (
            apigw_event
            .get("requestContext", {})
            .get("authorizer", {})
            .get("jwt", {})
            .get("claims", {})
        )
        if claims:
            return UserClaims(
                user_id=claims.get("sub", ""),
                email=claims.get("email", ""),
                groups=_parse_groups(claims.get("cognito:groups")),
            )

    # Local development bypass
    if os.environ.get("AUTH_BYPASS", "").lower() == "true":
        return UserClaims(
            user_id="dev-user-local",
            email="dev@local",
            groups=["admin"],
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated. Set AUTH_BYPASS=true for local development.",
    )


async def require_admin(user: UserClaims = Depends(get_current_user)) -> UserClaims:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    return user
