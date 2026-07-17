"""
Cognito JWT authentication for the Corporate API.

Moved to aiplatform/auth/cognito.py — the logic is pool-agnostic (it only
trusts whatever claims API Gateway's JWT authorizer already validated), so
it's shared with apps/knowledge_platform and apps/rag_demo rather than
duplicated per app. Re-exported here so existing imports in this app keep
working unchanged.
"""

from aiplatform.auth.cognito import UserClaims, get_current_user, require_admin

__all__ = ["UserClaims", "get_current_user", "require_admin"]
