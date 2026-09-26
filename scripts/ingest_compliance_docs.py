"""
Ingest /compliance/*.md documents into the Knowledge Platform vector index.

Documents are indexed with category="compliance" and appear in the Skills Hub
alongside engineering skills. They are also found by the AI Chat (which searches
all indexed content).

Dedup via SHA-256: unchanged files are skipped automatically by ingest_skill().

Usage:
    uv run python scripts/ingest_compliance_docs.py            # ingest all
    uv run python scripts/ingest_compliance_docs.py --dry-run  # preview only

Cost: ~$0.001 per document (text-embedding-3-small)
"""

import argparse
import sys
from pathlib import Path

import httpx
from _aws import require_env

API_URL = require_env("API_BASE")
INGEST_ENDPOINT = f"{API_URL}/api/v1/kp/ingest-skill"

COMPLIANCE_DIR = Path(__file__).parent.parent / "compliance"

# Explicit titles for files where simple title-casing would be wrong (acronyms, etc.)
_TITLE_OVERRIDES: dict[str, str] = {
    "ROPA": "ROPA — Record of Processing Activities",
    "AI_LIMITATIONS": "AI Limitations and Disclaimers",
    "MODEL_CARD": "Model Card",
    "PROCESSORS": "Sub-Processor Documentation (GDPR Art. 28)",
    "ACCEPTABLE_USE_POLICY": "Acceptable Use Policy",
    "INCIDENT_RESPONSE": "Incident Response Plan",
    "SECURITY_CONTROLS": "Security Controls Evidence Map",
    "DATA_RETENTION": "Data Retention Summary",
}


def derive_title(stem: str) -> str:
    if stem in _TITLE_OVERRIDES:
        return _TITLE_OVERRIDES[stem]
    return stem.replace("_", " ").title()


def ingest_doc(path: Path, dry_run: bool) -> str:
    content = path.read_text(encoding="utf-8")
    title = derive_title(path.stem)
    source_path = f"compliance/{path.stem}"

    if dry_run:
        print(f"  [dry-run] {path.name} → '{title}' ({len(content)} chars)")
        return "dry-run"

    payload = {
        "title": title,
        "content": content,
        "source_path": source_path,
        "category": "compliance",
    }

    with httpx.Client(timeout=60.0) as client:
        resp = client.post(INGEST_ENDPOINT, json=payload)

    if resp.status_code == 200:
        data = resp.json()
        if data.get("skipped"):
            return "skipped"
        return f"ok ({data.get('chunks_created', 0)} chunks)"
    return f"error {resp.status_code}: {resp.text[:120]}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest compliance docs into vector index")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no API calls")
    args = parser.parse_args()

    docs = sorted(COMPLIANCE_DIR.glob("*.md"))
    if not docs:
        print(f"No .md files found in {COMPLIANCE_DIR}")
        sys.exit(1)

    print("Compliance Document Indexer")
    print(f"  source : {COMPLIANCE_DIR}")
    print(f"  target : {INGEST_ENDPOINT}")
    print(f"  files  : {len(docs)}")
    print(f"  dry-run: {args.dry_run}")
    print()

    ingested = skipped = errors = 0

    for path in docs:
        result = ingest_doc(path, args.dry_run)
        print(f"  [{result}] {path.name}")

        if result.startswith("ok"):
            ingested += 1
        elif result in ("skipped", "dry-run"):
            skipped += 1
        else:
            errors += 1

    print(f"\nDone: total={len(docs)}  ingested={ingested}  skipped={skipped}  errors={errors}")


if __name__ == "__main__":
    main()
