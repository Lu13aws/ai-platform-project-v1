#!/usr/bin/env python3
"""
Manually ingest a local regulatory PDF into the Regulatory Radar pipeline.

Use this for sources that cannot be scraped automatically (e.g. EUR-Lex documents
that block automated access). Download the PDF manually from the official source,
then run this script to feed it into the pipeline.

What this does:
  1. Extracts text from the local PDF using pdfplumber
  2. Computes SHA-256 hash — compares with the latest stored version
  3. If new or changed: uploads PDF to S3, inserts a RegulatoryDocument record
  4. The Regulatory Analyzer picks it up on the next pipeline run (or immediately
     if you trigger the pipeline manually afterwards)

Usage:
    uv run python scripts/ingest_regulatory_pdf.py <pdf_path> <source_name> <domain>

    domain must be one of: AI | Privacy | Cybersecurity | Compliance

Examples:
    uv run python scripts/ingest_regulatory_pdf.py "C:/docs/EU-AI-Act.pdf" "EU AI Act" "AI"
    uv run python scripts/ingest_regulatory_pdf.py "C:/docs/GDPR.pdf" "GDPR" "Privacy"
    uv run python scripts/ingest_regulatory_pdf.py "C:/docs/FINMA_2025.pdf" "FINMA Risk Monitor 2025" "Compliance"

To run the analyzer + reporter immediately after ingestion:
    uv run python -m apps.regulatory_pipeline.lambda_handler
"""

import asyncio
import hashlib
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from aiplatform.storage.database import get_async_session
from aiplatform.storage.regulatory_models import RegulatoryDocument, RegulatorySource
from aiplatform.storage.s3 import S3Client
from sqlalchemy import select, update

_VALID_DOMAINS = {"AI", "Privacy", "Cybersecurity", "Compliance"}


def extract_pdf_text(path: Path) -> str:
    import pdfplumber

    pages = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text(x_tolerance=2, y_tolerance=3) or ""
            if text.strip():
                pages.append(text)
    return "\n\n".join(pages)


async def ingest(pdf_path: Path, source_name: str, domain: str) -> None:
    print(f"\nIngesting: {pdf_path.name}")
    print(f"  Source : {source_name}")
    print(f"  Domain : {domain}")

    # Step 1: extract text
    print("\n  [1/4] Extracting text with pdfplumber...")
    text = extract_pdf_text(pdf_path)
    if not text.strip():
        print("  [err] No text extracted. Is the PDF a scanned image without OCR?")
        sys.exit(1)
    print(f"        {len(text):,} chars extracted")

    content_hash = hashlib.sha256(text.encode()).hexdigest()
    print(f"        hash: {content_hash[:16]}...")

    slug = re.sub(r"[^a-z0-9]+", "-", source_name.lower()).strip("-")
    manual_url = f"manual://{slug}"

    async with get_async_session() as session:
        # Step 2: ensure source exists (active=False so auto-collector skips it)
        source = await session.scalar(
            select(RegulatorySource).where(RegulatorySource.name == source_name)
        )
        if source is None:
            source = RegulatorySource(
                name=source_name,
                url=manual_url,
                source_type="pdf",
                domain=domain,
                active=False,
                created_at=datetime.now(UTC),
            )
            session.add(source)
            await session.flush()
            print(f"\n  [2/4] Source created: '{source_name}' (manual, id={source.id})")
        else:
            print(f"\n  [2/4] Source found: '{source_name}' (id={source.id})")

        # Step 3: check if this version is already stored
        latest = await session.scalar(
            select(RegulatoryDocument).where(
                RegulatoryDocument.source_id == source.id,
                RegulatoryDocument.is_latest.is_(True),
            )
        )

        if latest and latest.content_hash == content_hash:
            print("\n  [skip] Document unchanged — same hash already stored. Nothing to do.")
            return

        # Step 4: upload to S3
        print("\n  [3/4] Uploading to S3...")
        now = datetime.now(UTC)
        s3_key = f"regulatory/raw/{now.year}/{now.month:02d}/{slug}/{content_hash[:12]}.pdf"

        s3 = S3Client()
        raw_bytes = pdf_path.read_bytes()
        await s3.upload(s3_key, raw_bytes, "application/pdf")
        print(f"        s3://{s3_key}")

        # Mark previous version as no longer latest
        if latest:
            await session.execute(
                update(RegulatoryDocument)
                .where(RegulatoryDocument.id == latest.id)
                .values(is_latest=False)
            )

        # Insert new document record
        session.add(RegulatoryDocument(
            source_id=source.id,
            content_hash=content_hash,
            s3_key=s3_key,
            text_length=len(text),
            is_latest=True,
            fetched_at=now,
        ))

        action = "updated" if latest else "first"
        print(f"\n  [4/4] RegulatoryDocument record saved ({action} version)")

    print("""
  Done.

  Next step — trigger the analyzer to generate the impact summary:
    uv run python -m apps.regulatory_pipeline.lambda_handler

  Or wait for the Lambda to run automatically on the 1st of next month.
""")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: uv run python scripts/ingest_regulatory_pdf.py <pdf_path> <source_name> <domain>")
        print(f"       domain: {' | '.join(sorted(_VALID_DOMAINS))}")
        print()
        print("Examples:")
        print('  uv run python scripts/ingest_regulatory_pdf.py "C:/docs/EU-AI-Act.pdf" "EU AI Act" "AI"')
        print('  uv run python scripts/ingest_regulatory_pdf.py "C:/docs/GDPR.pdf" "GDPR" "Privacy"')
        sys.exit(1)

    pdf_path = Path(sys.argv[1])
    if not pdf_path.exists():
        print(f"Error: file not found: {pdf_path}")
        sys.exit(1)
    if pdf_path.suffix.lower() != ".pdf":
        print(f"Error: expected a .pdf file, got: {pdf_path.suffix}")
        sys.exit(1)
    if sys.argv[3] not in _VALID_DOMAINS:
        print(f"Error: invalid domain '{sys.argv[3]}'. Must be one of: {', '.join(sorted(_VALID_DOMAINS))}")
        sys.exit(1)

    asyncio.run(ingest(pdf_path, sys.argv[2], sys.argv[3]))
