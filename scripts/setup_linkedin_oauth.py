"""
One-time LinkedIn OAuth setup — stores credentials in AWS Secrets Manager.

Run this ONCE locally before deploying the content creator pipeline:
    uv run python scripts/setup_linkedin_oauth.py

Prerequisites:
  1. Create a LinkedIn Developer App at https://developer.linkedin.com/apps
  2. Add product "Share on LinkedIn" (grants w_member_social scope)
  3. Set redirect URL to: http://localhost:8080/callback
  4. Set LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET in your .env

What this does:
  - Opens browser with LinkedIn OAuth URL
  - Starts local HTTP server to catch the callback with the auth code
  - Exchanges code for access_token + refresh_token
  - Fetches your LinkedIn person URN
  - Stores everything in AWS Secrets Manager as "linkedin/credentials"
"""

import json
import sys
import threading
import urllib.parse
import webbrowser
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import boto3
import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from aiplatform.settings import settings

REGION = "eu-central-1"
SECRET_NAME = "linkedin/credentials"
REDIRECT_URI = "http://localhost:8080/callback"
SCOPES = "w_member_social openid profile"

_auth_code: str | None = None
_server_error: str | None = None


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global _auth_code, _server_error
        parsed = urllib.parse.urlparse(self.path)
        params = dict(urllib.parse.parse_qsl(parsed.query))
        if "code" in params:
            _auth_code = params["code"]
            body = b"<h2>Authorization successful! You can close this tab.</h2>"
            self.send_response(200)
        elif "error" in params:
            _server_error = params.get("error_description", params["error"])
            body = f"<h2>Error: {_server_error}</h2>".encode()
            self.send_response(400)
        else:
            body = b"<h2>Unexpected callback.</h2>"
            self.send_response(400)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass  # Suppress server logs


def _get_client_credentials() -> tuple[str, str]:
    client_id = settings.linkedin_client_id
    client_secret = settings.linkedin_client_secret.get_secret_value()
    if not client_id:
        client_id = input("LinkedIn Client ID: ").strip()
    if not client_secret:
        client_secret = input("LinkedIn Client Secret: ").strip()
    return client_id, client_secret


def main() -> None:
    print("=== LinkedIn OAuth Setup ===\n")

    client_id, client_secret = _get_client_credentials()

    # Build OAuth URL
    auth_url = (
        "https://www.linkedin.com/oauth/v2/authorization"
        f"?response_type=code"
        f"&client_id={client_id}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
        f"&scope={urllib.parse.quote(SCOPES)}"
    )

    print(f"Opening browser for LinkedIn authorization...")
    print(f"If browser doesn't open, visit:\n  {auth_url}\n")

    # Start local callback server in background thread
    server = HTTPServer(("localhost", 8080), _CallbackHandler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()

    webbrowser.open(auth_url)
    print("Waiting for authorization (complete in browser)...")
    thread.join(timeout=120)
    server.server_close()

    if _server_error:
        print(f"\n[error] LinkedIn authorization failed: {_server_error}")
        sys.exit(1)
    if not _auth_code:
        print("\n[error] No authorization code received (timeout or browser issue).")
        sys.exit(1)

    print("[ok] Authorization code received")

    # Exchange code for tokens
    print("Exchanging code for tokens...")
    with httpx.Client(timeout=30.0) as client:
        token_resp = client.post(
            "https://www.linkedin.com/oauth/v2/accessToken",
            data={
                "grant_type": "authorization_code",
                "code": _auth_code,
                "redirect_uri": REDIRECT_URI,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    if token_resp.status_code != 200:
        print(f"\n[error] Token exchange failed: {token_resp.status_code} {token_resp.text}")
        sys.exit(1)

    token_data = token_resp.json()
    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token", "")
    expires_in = token_data.get("expires_in", 5183999)  # default 60 days
    token_expires_at = (datetime.now(UTC) + timedelta(seconds=expires_in)).isoformat()

    print("[ok] Access token obtained")

    # Fetch person URN via OpenID userinfo
    print("Fetching LinkedIn person URN...")
    with httpx.Client(timeout=30.0) as client:
        profile_resp = client.get(
            "https://api.linkedin.com/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    if profile_resp.status_code != 200:
        print(f"\n[error] Could not fetch profile: {profile_resp.status_code} {profile_resp.text}")
        sys.exit(1)

    profile = profile_resp.json()
    person_sub = profile.get("sub", "")  # OpenID sub = numeric person ID
    person_urn = f"urn:li:person:{person_sub}"
    name = profile.get("name", "Unknown")

    print(f"[ok] Authenticated as: {name} ({person_urn})")

    # Store in Secrets Manager
    credentials = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_expires_at": token_expires_at,
        "person_urn": person_urn,
        "client_id": client_id,
        "client_secret": client_secret,
    }

    sm = boto3.client("secretsmanager", region_name=REGION)
    try:
        sm.create_secret(
            Name=SECRET_NAME,
            Description="LinkedIn OAuth credentials for Content Creator pipeline",
            SecretString=json.dumps(credentials),
        )
        print(f"[ok] Secret created: {SECRET_NAME}")
    except sm.exceptions.ResourceExistsException:
        sm.put_secret_value(
            SecretId=SECRET_NAME,
            SecretString=json.dumps(credentials),
        )
        print(f"[ok] Secret updated: {SECRET_NAME}")

    print(f"\n=== Setup complete ===")
    print(f"  Person URN      : {person_urn}")
    print(f"  Token expires   : {token_expires_at}")
    print(f"  Secret name     : {SECRET_NAME}")
    print(f"\nRun deploy next:")
    print(f"  uv run python scripts/deploy_content_pipeline.py")


if __name__ == "__main__":
    main()
