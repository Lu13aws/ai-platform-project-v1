"""
LinkedInPublisherAgent — posts generated content to LinkedIn via the Posts API.

Token management:
  - Credentials stored in AWS Secrets Manager (secret name: linkedin/credentials)
  - Access tokens expire after 60 days — automatically refreshed using refresh_token
  - Updated credentials written back to Secrets Manager after refresh

LinkedIn Posts API (v2):
  POST https://api.linkedin.com/rest/posts
  Requires scope: w_member_social
"""

import json
import os
from datetime import UTC, datetime

import boto3
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from aiplatform.settings import settings
from aiplatform.storage.content_models import LinkedInPost

_LINKEDIN_API = "https://api.linkedin.com/v2/ugcPosts"
_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"


def _load_credentials(sm_client, secret_name: str) -> dict:
    resp = sm_client.get_secret_value(SecretId=secret_name)
    return json.loads(resp["SecretString"])


def _save_credentials(sm_client, secret_name: str, creds: dict) -> None:
    sm_client.put_secret_value(
        SecretId=secret_name,
        SecretString=json.dumps(creds),
    )


def _days_until_expiry(creds: dict) -> int:
    expires_at = creds.get("token_expires_at", "")
    if not expires_at:
        return 0
    try:
        exp = datetime.fromisoformat(expires_at)
        return max(0, (exp - datetime.now(UTC)).days)
    except Exception:
        return 0


def _is_token_expired(creds: dict) -> bool:
    return _days_until_expiry(creds) < 7


def _refresh_access_token(creds: dict) -> dict:
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            _TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": creds["refresh_token"],
                "client_id": creds["client_id"],
                "client_secret": creds["client_secret"],
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    resp.raise_for_status()
    data = resp.json()
    from datetime import timedelta
    expires_in = data.get("expires_in", 5183999)
    creds["access_token"] = data["access_token"]
    if "refresh_token" in data:
        creds["refresh_token"] = data["refresh_token"]
    creds["token_expires_at"] = (datetime.now(UTC) + timedelta(seconds=expires_in)).isoformat()
    return creds


class LinkedInPublisherAgent:
    def __init__(self) -> None:
        self._secret_name = os.environ.get("LINKEDIN_SECRET_NAME", "linkedin/credentials")
        self._sm = boto3.client("secretsmanager", region_name=settings.aws_region)

    async def run(self, session: AsyncSession, post: LinkedInPost) -> bool:
        topic_arn = os.environ.get("SNS_TOPIC_ARN", "")

        try:
            creds = _load_credentials(self._sm, self._secret_name)
        except Exception as exc:
            print(f"  [linkedin] Could not load credentials: {exc}")
            return False

        days_left = _days_until_expiry(creds)
        has_refresh = bool(creds.get("refresh_token"))

        # Warn via SNS if token expires within 30 days and no refresh token available
        if days_left <= 30 and not has_refresh and topic_arn:
            subject = f"[AI Platform] LinkedIn token expires in {days_left} days — action required"
            message = (
                f"LinkedIn Access Token Expiry Warning\n"
                f"{'=' * 40}\n\n"
                f"Days remaining : {days_left}\n"
                f"Expires at     : {creds.get('token_expires_at', 'unknown')}\n\n"
                f"No refresh token is available. You must re-run the OAuth setup\n"
                f"before the token expires to avoid losing LinkedIn publishing:\n\n"
                f"  uv run python scripts/setup_linkedin_oauth.py\n"
            )
            try:
                boto3.client("sns", region_name=settings.aws_region).publish(
                    TopicArn=topic_arn, Subject=subject, Message=message
                )
                print(f"  [linkedin] Token expiry warning sent — {days_left} days left")
            except Exception as exc:
                print(f"  [linkedin] Could not send expiry warning: {exc}")

        # Refresh token if close to expiry (only possible when refresh_token exists)
        if _is_token_expired(creds):
            if not has_refresh:
                print("  [linkedin] Token expired and no refresh token — cannot publish")
                return False
            print("  [linkedin] Access token expiring — refreshing...")
            try:
                creds = _refresh_access_token(creds)
                _save_credentials(self._sm, self._secret_name, creds)
                print("  [linkedin] Token refreshed and saved")
            except Exception as exc:
                print(f"  [linkedin] Token refresh failed: {exc}")
                return False

        access_token = creds["access_token"]
        person_urn = creds["person_urn"]

        payload = {
            "author": person_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": post.content},
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
            },
        }

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        }

        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(_LINKEDIN_API, json=payload, headers=headers)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            print(f"  [linkedin] API error {exc.response.status_code}: {exc.response.text}")
            return False
        except Exception as exc:
            print(f"  [linkedin] Request failed: {exc}")
            return False

        # ugcPosts returns post URN in the response body as "id"
        post_id = resp.json().get("id", resp.headers.get("x-restli-id", ""))
        post_url = f"https://www.linkedin.com/feed/update/{post_id}" if post_id else ""

        print(f"  [linkedin] Post published: {post_url or '(URL unavailable)'}")

        # Update DB record
        post.linkedin_post_id = post_id
        post.linkedin_post_url = post_url
        post.posted_at = datetime.now(UTC)
        await session.flush()

        # Send SNS notification
        if topic_arn:
            preview = post.content[:300].replace("\n", " ")
            subject = f"LinkedIn post published: {post.company} ({post.angle})"[:100]
            message = (
                f"Content Creator — LinkedIn Post Published\n"
                f"{'=' * 40}\n\n"
                f"Company : {post.company}\n"
                f"Domain  : {post.domain}\n"
                f"Angle   : {post.angle}\n"
                f"URL     : {post_url}\n\n"
                f"Preview:\n{preview}...\n"
            )
            try:
                boto3.client("sns").publish(TopicArn=topic_arn, Subject=subject, Message=message)
                print("  [linkedin] SNS notification sent")
            except Exception as exc:
                print(f"  [linkedin] SNS failed: {exc}")

        return True
