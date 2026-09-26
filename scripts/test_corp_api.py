"""
Phase 6 — Test script: login, ingest, query, sources, audit.

Usage:
    uv run python scripts/test_corp_api.py
"""

import asyncio
from pathlib import Path

import boto3
import httpx

CORP_API = "https://3odo5043uh.execute-api.eu-central-1.amazonaws.com/api/v1/corp"
COGNITO_CLIENT_ID = "3vptapgfltcov01fo7enpld3it"
REGION = "eu-central-1"


def get_token(username: str, password: str) -> str:
    cognito = boto3.client("cognito-idp", region_name=REGION)
    resp = cognito.initiate_auth(
        AuthFlow="USER_PASSWORD_AUTH",
        ClientId=COGNITO_CLIENT_ID,
        AuthParameters={"USERNAME": username, "PASSWORD": password},
    )
    return resp["AuthenticationResult"]["IdToken"]


async def main() -> None:
    # --- Login ---
    print("=== LOGIN ===")
    import os
    password = os.environ.get("CORP_ADMIN_PASSWORD")
    if not password:
        password = input("Admin password: ")

    token = get_token("luciano.10@hotmail.de", password)
    print(f"Token obtained ({len(token)} chars)")

    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(timeout=60) as client:

        # --- Auth check ---
        print("\n=== AUTH CHECK ===")
        r = await client.get(f"{CORP_API}/health/auth", headers=headers)
        print(r.json())

        # --- Ingest CLAUDE.md ---
        print("\n=== INGEST CLAUDE.md ===")
        claude_md = Path("CLAUDE.md").read_text(encoding="utf-8")
        r = await client.post(f"{CORP_API}/ingest", headers=headers, json={
            "source_uri": "github://ai-platform-project-v1/CLAUDE.md",
            "title": "AI Platform Project Instructions (CLAUDE.md)",
            "content": claude_md,
            "app_name": "corp",
        })
        print(r.status_code, r.text[:500] if r.status_code != 200 else r.json())

        # --- Ingest README.md ---
        print("\n=== INGEST README.md ===")
        readme = Path("README.md").read_text(encoding="utf-8")
        r = await client.post(f"{CORP_API}/ingest", headers=headers, json={
            "source_uri": "github://ai-platform-project-v1/README.md",
            "title": "AI Platform README",
            "content": readme,
            "app_name": "corp",
        })
        print(r.status_code, r.json())

        # --- Sources ---
        print("\n=== SOURCES ===")
        r = await client.get(f"{CORP_API}/sources", headers=headers)
        sources = r.json()
        print(f"Total: {sources['total']}")
        for s in sources["sources"]:
            print(f"  - {s['title']} ({s['source_uri']})")

        # --- Query ---
        print("\n=== QUERY ===")
        r = await client.post(f"{CORP_API}/query", headers=headers, json={
            "question": "What is the current status of Phase 6?",
            "top_k": 3,
        })
        result = r.json()
        print(f"Answer: {result['answer'][:300]}...")
        print(f"Sources: {[s['title'] for s in result['sources']]}")

        # --- GDPR Art. 17 Deletion ---
        print("\n=== DELETE DOCUMENT (GDPR Art. 17) ===")
        # Ingest a throwaway document first
        r = await client.post(f"{CORP_API}/ingest", headers=headers, json={
            "source_uri": "github://ai-platform-project-v1/TEST_DELETE.md",
            "title": "Throwaway Test Document",
            "content": "This document exists only to be deleted as part of GDPR Art. 17 testing.",
            "app_name": "corp",
        })
        doc_id = r.json()["document_id"]
        print(f"Ingested throwaway doc: {doc_id}")

        r = await client.delete(f"{CORP_API}/documents/{doc_id}", headers=headers)
        print(r.status_code, r.json())

        # Confirm it's gone from sources
        r = await client.get(f"{CORP_API}/sources", headers=headers)
        uris = [s["source_uri"] for s in r.json()["sources"]]
        deleted_gone = "github://ai-platform-project-v1/TEST_DELETE.md" not in uris
        print(f"Deleted doc absent from sources: {deleted_gone}")

        # --- Audit ---
        print("\n=== AUDIT LOG ===")
        r = await client.get(f"{CORP_API}/audit", headers=headers)
        audit = r.json()
        print(f"Total audit entries: {audit['total']}")
        for e in audit["entries"][:8]:
            print(f"  {e['created_at']} | {e['email']} | {e['action']} | {e.get('resource', '')}")


if __name__ == "__main__":
    asyncio.run(main())
