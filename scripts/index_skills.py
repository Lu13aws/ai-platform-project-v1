"""
Index all SKILL.md files from personal-data-engineering-toolkit into pgvector.

Sends skill content via HTTP to the /api/v1/kp/ingest-skill endpoint so the Lambda
(with VPC access to RDS) handles the DB writes — local DB connectivity not required.

Usage:
    uv run python scripts/index_skills.py
    uv run python scripts/index_skills.py --api-base https://<API_ID>.execute-api.eu-central-1.amazonaws.com

Re-run at any time — SHA-256 dedup skips unchanged files automatically.
"""

import argparse
import sys
from pathlib import Path

import httpx
from _aws import env

SKILLS_DIR = Path(__file__).resolve().parents[2] / "personal-data-engineering-toolkit" / "skills"  # sibling repo
DEFAULT_API_BASE = env("API_BASE") or None  # from .env
ENDPOINT = "/api/v1/kp/ingest-skill"


def index_skills(api_base: str) -> None:
    if not SKILLS_DIR.exists():
        print(f"Skills directory not found: {SKILLS_DIR}")
        sys.exit(1)

    url = f"{api_base.rstrip('/')}{ENDPOINT}"
    print(f"Indexing skills from : {SKILLS_DIR}")
    print(f"Target API           : {url}")
    print()

    ingested = skipped = errors = 0
    skill_files = sorted(SKILLS_DIR.rglob("SKILL.md"))
    print(f"Found {len(skill_files)} SKILL.md files")
    print()

    with httpx.Client(timeout=60.0) as client:
        for path in skill_files:
            relative = path.relative_to(SKILLS_DIR)
            parts = relative.parts
            category = parts[0] if len(parts) >= 2 else "other"
            skill_name = parts[1] if len(parts) >= 3 else path.parent.name

            content = path.read_text(encoding="utf-8", errors="replace")

            try:
                resp = client.post(url, json={
                    "title": skill_name,
                    "content": content,
                    "source_path": str(relative).replace("\\", "/"),
                    "category": category,
                })
                resp.raise_for_status()
                data = resp.json()
                if data.get("skipped"):
                    skipped += 1
                    print(f"  [skip] {skill_name}")
                else:
                    ingested += 1
                    print(f"  [ok]   {skill_name} ({category}) -> {data.get('chunks_created')} chunks")
            except httpx.HTTPStatusError as e:
                errors += 1
                print(f"  [err]  {skill_name}: HTTP {e.response.status_code} — {e.response.text[:120]}")
            except Exception as e:
                errors += 1
                print(f"  [err]  {skill_name}: {e}")

    print()
    print(f"Done: ingested={ingested}  skipped={skipped}  errors={errors}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base", default=DEFAULT_API_BASE, help="default: API_BASE from .env")
    args = parser.parse_args()
    if not args.api_base:
        parser.error("--api-base or API_BASE in .env is required")
    index_skills(args.api_base)
