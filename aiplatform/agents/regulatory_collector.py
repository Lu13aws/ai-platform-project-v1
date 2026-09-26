"""
Regulatory Collector Agent — fetches regulatory documents and detects new versions.

For each active RegulatorySource:
  1. Download the document (HTML or PDF)
  2. Extract plain text and compute SHA-256 hash
  3. Compare with the latest stored version
  4. If changed or new → upload raw file to S3, insert new RegulatoryDocument record
  5. If unchanged → skip (zero cost)

Uses the two-phase pattern: all HTTP first (no open DB session), then a short
DB session to save. Prevents long-running transactions during network I/O.
"""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from io import BytesIO

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from aiplatform.agents.fetch_utils import check_response_size
from aiplatform.storage.regulatory_models import RegulatoryDocument, RegulatorySource
from aiplatform.storage.s3 import S3Client

_REQUEST_TIMEOUT = 60.0
_MAX_TEXT_LENGTH = 500_000  # truncate very long documents before hashing


@dataclass
class _FetchedDocument:
    source: RegulatorySource
    raw_bytes: bytes
    text_content: str
    content_hash: str
    extension: str  # "html" or "pdf"


@dataclass
class RegulatoryCollectorResult:
    sources_checked: int = 0
    new_versions: int = 0
    unchanged: int = 0
    errors: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return (
            f"checked={self.sources_checked} "
            f"new_versions={self.new_versions} "
            f"unchanged={self.unchanged} "
            f"errors={len(self.errors)}"
        )


class RegulatoryCollectorAgent:
    async def run(self, session: AsyncSession) -> RegulatoryCollectorResult:
        result = RegulatoryCollectorResult()

        sources = (
            await session.scalars(
                select(RegulatorySource).where(RegulatorySource.active.is_(True))
            )
        ).all()

        # Phase 1: fetch all documents via HTTP (no open DB transaction)
        fetched: list[_FetchedDocument] = []
        async with httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "AI-Platform-Regulatory-Radar/1.0"},
        ) as client:
            for source in sources:
                try:
                    doc = await self._fetch(client, source)
                    fetched.append(doc)
                    print(f"  [fetch] {source.name}: {len(doc.text_content):,} chars extracted")
                except Exception as exc:
                    msg = f"{source.name}: {type(exc).__name__}: {exc}"
                    result.errors.append(msg)
                    print(f"  [err]   {msg}")

        # Phase 2: compare hashes, save new versions (short DB session)
        s3 = S3Client()
        now = datetime.now(UTC)

        for doc in fetched:
            result.sources_checked += 1
            source_name = doc.source.name  # capture before any rollback expires the object
            try:
                latest = await self._get_latest(session, doc.source.id)

                if latest and latest.content_hash == doc.content_hash:
                    result.unchanged += 1
                    print(f"  [skip]  {source_name}: unchanged")
                    doc.source.last_checked_at = now
                    await session.flush()
                    continue

                # New or changed version — upload raw file to S3
                s3_key = _build_s3_key(doc, now)
                content_type = "application/pdf" if doc.extension == "pdf" else "text/html"
                await s3.upload(s3_key, doc.raw_bytes, content_type)

                # Mark previous version as no longer latest
                if latest:
                    await session.execute(
                        update(RegulatoryDocument)
                        .where(RegulatoryDocument.id == latest.id)
                        .values(is_latest=False)
                    )

                # Insert new version
                session.add(RegulatoryDocument(
                    source_id=doc.source.id,
                    content_hash=doc.content_hash,
                    s3_key=s3_key,
                    text_length=len(doc.text_content),
                    is_latest=True,
                    fetched_at=now,
                ))

                doc.source.last_checked_at = now
                await session.flush()
                result.new_versions += 1
                action = "new" if not latest else "updated"
                print(f"  [save]  {source_name}: {action} version -> s3://{s3_key}")

            except Exception as exc:
                await session.rollback()
                msg = f"{source_name} (save): {type(exc).__name__}: {exc}"
                result.errors.append(msg)
                print(f"  [err]   {msg}")

        return result

    async def _fetch(self, client: httpx.AsyncClient, source: RegulatorySource) -> _FetchedDocument:
        response = await client.get(source.url)
        response.raise_for_status()
        check_response_size(response)

        if source.source_type == "pdf":
            text = _extract_pdf_text(response.content)
            ext = "pdf"
        else:
            text = _extract_html_text(response.text)
            ext = "html"

        text = text[:_MAX_TEXT_LENGTH]
        content_hash = hashlib.sha256(text.encode()).hexdigest()

        return _FetchedDocument(
            source=source,
            raw_bytes=response.content,
            text_content=text,
            content_hash=content_hash,
            extension=ext,
        )

    async def _get_latest(
        self, session: AsyncSession, source_id: object
    ) -> RegulatoryDocument | None:
        return await session.scalar(
            select(RegulatoryDocument)
            .where(
                RegulatoryDocument.source_id == source_id,
                RegulatoryDocument.is_latest.is_(True),
            )
        )


# ── Helpers ────────────────────────────────────────────────────────────────────

def _extract_html_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_pdf_text(raw: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(raw))
    pages = []
    for page in reader.pages:
        t = page.extract_text() or ""
        if t.strip():
            pages.append(t)
    return "\n\n".join(pages)


def _build_s3_key(doc: _FetchedDocument, now: datetime) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", doc.source.name.lower()).strip("-")
    return f"regulatory/raw/{now.year}/{now.month:02d}/{slug}/{doc.content_hash[:12]}.{doc.extension}"
