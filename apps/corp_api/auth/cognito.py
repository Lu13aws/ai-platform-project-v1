"""
Cognito JWT authentication for the Corporate API.

Production (Lambda + API Gateway):
  API Gateway JWT Authorizer validates the token — Lambda reads pre-validated claims
  from the API Gateway event context.

Local development:
  Set AUTH_BYPASS=true to skip auth (admin identity assumed).
  Or send a valid Cognito JWT as Authorization: Bearer <token>.
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
        return "admin" in self.groups

    @property
    def is_demo_user(self) -> bool:
        return "demo_user" in self.groups or self.is_admin


def _parse_groups(raw: str | list | None) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    # Cognito returns space-separated groups as a string
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
