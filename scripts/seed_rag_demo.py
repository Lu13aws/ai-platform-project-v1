#!/usr/bin/env python3
"""
Download and ingest public demo documents for the RAG demo.

Documents are saved to data/raw/rag_demo/ and ingested via the running API server.
Re-running is safe: already-downloaded files are skipped, and unchanged documents
are skipped by the deduplication logic in the ingest pipeline.

Usage:
    uv run python scripts/seed_rag_demo.py
    uv run python scripts/seed_rag_demo.py --api-url http://localhost:8000
    uv run python scripts/seed_rag_demo.py --download-only
"""

import argparse
import sys
from pathlib import Path

import httpx

RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "rag_demo"

DOCUMENTS = [
    {
        "name": "NIST SP 800-61r2 — Computer Security Incident Handling Guide",
        "filename": "nist_sp800_61r2.pdf",
        "url": "https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-61r2.pdf",
        "title": "NIST SP 800-61r2: Computer Security Incident Handling Guide",
        "metadata": {"category": "security", "source": "nist.gov", "year": 2012},
    },
    {
        "name": "NIST Cybersecurity Framework v1.1",
        "filename": "nist_csf_v1.1.pdf",
        "url": "https://nvlpubs.nist.gov/nistpubs/CSWP/NIST.CSWP.04162018.pdf",
        "title": "NIST Cybersecurity Framework v1.1",
        "metadata": {"category": "security", "source": "nist.gov", "year": 2018},
    },
    {
        "name": "AWS Well-Architected Framework",
        "filename": "aws_well_architected.pdf",
        "url": "https://docs.aws.amazon.com/pdfs/wellarchitected/latest/framework/wellarchitected-framework.pdf",
        "title": "AWS Well-Architected Framework",
        "metadata": {"category": "cloud", "source": "aws.amazon.com", "year": 2023},
    },
]


def download_file(doc: dict, target_dir: Path) -> Path:
    path = target_dir / doc["filename"]
    if path.exists():
        size_kb = path.stat().st_size / 1024
        print(f"  [skip] {doc['filename']} already exists ({size_kb:.0f} KB)")
        return path

    print(f"  [download] {doc['name']} ...")

    with httpx.Client(timeout=120, follow_redirects=True) as client:
        response = client.get(doc["url"], headers={"User-Agent": "ai-platform-seed/1.0"})
        response.raise_for_status()
        path.write_bytes(response.content)

    size_kb = path.stat().st_size / 1024
    print(f"  [ok] {path.name} ({size_kb:.0f} KB)")
    return path


def ingest_document(path: Path, doc: dict, api_url: str) -> dict:
    payload = {
        "source_uri": str(path),
        "title": doc["title"],
        "metadata": doc["metadata"],
    }
    with httpx.Client(timeout=300) as client:
        response = client.post(f"{api_url}/api/v1/ingest", json=payload)
        response.raise_for_status()
        return response.json()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed RAG demo with public documents")
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="Base URL of the running RAG demo API (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--download-only",
        action="store_true",
        help="Only download files, skip ingestion",
    )
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\nTarget directory: {RAW_DIR}")
    print(f"API: {args.api_url}\n")

    results = {"ingested": 0, "skipped": 0, "failed": 0}

    for doc in DOCUMENTS:
        print(f"--- {doc['name']} ---")
        try:
            path = download_file(doc, RAW_DIR)

            if args.download_only:
                print()
                continue

            print("  [ingest] sending to API ...")
            result = ingest_document(path, doc, args.api_url)

            if result["skipped"]:
                print(f"  [skip] {result['message']}")
                results["skipped"] += 1
            else:
                print(f"  [ok] {result['chunks_created']} chunks created")
                print(f"       document_id: {result['document_id']}")
                results["ingested"] += 1

        except httpx.HTTPStatusError as exc:
            print(f"  [error] API returned {exc.response.status_code}: {exc.response.text[:200]}")
            results["failed"] += 1
        except Exception as exc:
            print(f"  [error] {type(exc).__name__}: {exc}")
            results["failed"] += 1

        print()

    print("=" * 50)
    print(f"Done: {results['ingested']} ingested  |  {results['skipped']} skipped  |  {results['failed']} failed")

    if results["failed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
