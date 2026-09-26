"""
Collector Agent — fetches articles from radar sources and stores them in raw_articles.

Handles:
  - RSS 2.0 and Atom feeds (parsed with stdlib xml.etree)
  - HTML pages (scraped with BeautifulSoup)

Change detection is built in: articles are skipped if the URL already exists
in raw_articles, so re-running the collector never produces duplicates.
"""

import hashlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from defusedxml.ElementTree import fromstring as safe_xml_fromstring
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aiplatform.agents.fetch_utils import check_response_size
from aiplatform.storage.radar_models import RadarSource, RawArticle

_RETENTION_DAYS = 30
_MAX_ARTICLES_PER_SOURCE = 20
_REQUEST_TIMEOUT = 30.0

_RSS_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
}


@dataclass
class _ArticleData:
    url: str
    title: str
    content: str
    signal_date: datetime


@dataclass
class CollectorResult:
    sources_processed: int = 0
    articles_inserted: int = 0
    articles_skipped: int = 0
    errors: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return (
            f"sources={self.sources_processed} "
            f"inserted={self.articles_inserted} "
            f"skipped={self.articles_skipped} "
            f"errors={len(self.errors)}"
        )


class CollectorAgent:
    async def run(self, session: AsyncSession) -> CollectorResult:
        result = CollectorResult()
        sources = (
            await session.scalars(select(RadarSource).where(RadarSource.active.is_(True)))
        ).all()

        # Phase 1: fetch all articles via HTTP (no open DB transaction)
        fetched: list[tuple[RadarSource, list[_ArticleData]]] = []
        async with httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "AI-Platform-Radar/1.0"},
        ) as client:
            for source in sources:
                try:
                    articles = await self._fetch(client, source)
                    fetched.append((source, articles))
                    result.sources_processed += 1
                    print(f"  [fetch] {source.name}: {len(articles)} articles fetched")
                except Exception as exc:
                    msg = f"{source.name}: {type(exc).__name__}: {exc}"
                    result.errors.append(msg)
                    print(f"  [err] {msg}")

        # Phase 2: save to DB (short transaction, no HTTP calls)
        for source, articles in fetched:
            try:
                inserted, skipped = await self._save(session, source, articles)
                source.last_fetched_at = datetime.now(UTC)
                await session.flush()  # surface constraint errors per source
                result.articles_inserted += inserted
                result.articles_skipped += skipped
                print(f"  [save] {source.name}: +{inserted} new, {skipped} skipped")
            except Exception as exc:
                await session.rollback()
                msg = f"{source.name} (save): {type(exc).__name__}: {exc}"
                result.errors.append(msg)
                print(f"  [err] {msg}")

        return result

    # ------------------------------------------------------------------
    # Fetch
    # ------------------------------------------------------------------

    async def _fetch(self, client: httpx.AsyncClient, source: RadarSource) -> list[_ArticleData]:
        if source.source_type == "rss" and source.feed_url:
            return await self._fetch_rss(client, source.feed_url)
        return await self._fetch_html(client, source.url)

    async def _fetch_rss(self, client: httpx.AsyncClient, feed_url: str) -> list[_ArticleData]:
        response = await client.get(feed_url)
        response.raise_for_status()
        check_response_size(response)

        root = safe_xml_fromstring(response.content)
        articles: list[_ArticleData] = []

        # RSS 2.0: <rss><channel><item>
        items = root.findall(".//item")

        # Atom: <feed><entry>
        if not items:
            items = root.findall(f".//{{{_RSS_NS['atom']}}}entry")

        for item in items[:_MAX_ARTICLES_PER_SOURCE]:
            article = self._parse_rss_item(item)
            if article:
                articles.append(article)

        return articles

    def _parse_rss_item(self, item: ET.Element) -> _ArticleData | None:
        def text(tag: str, ns: str | None = None) -> str:
            full_tag = f"{{{_RSS_NS[ns]}}}{tag}" if ns else tag
            el = item.find(full_tag)
            return (el.text or "").strip() if el is not None else ""

        title = text("title") or text("title", "atom")
        if not title:
            return None

        # Link: RSS 2.0 text content, Atom href attribute
        link = text("link")
        if not link:
            link_el = item.find(f"{{{_RSS_NS['atom']}}}link")
            link = (link_el.get("href", "") if link_el is not None else "")
        if not link:
            return None

        # Content: prefer full content, fall back to description/summary
        raw_content = (
            text("encoded", "content")
            or text("description")
            or text("summary", "atom")
        )
        content = BeautifulSoup(raw_content, "lxml").get_text(separator=" ", strip=True)
        combined = f"{title}. {content}".strip()

        # Date
        date_str = text("pubDate") or text("published", "atom") or text("date", "dc")
        signal_date = _parse_date(date_str)

        return _ArticleData(url=link, title=title, content=combined, signal_date=signal_date)

    async def _fetch_html(self, client: httpx.AsyncClient, url: str) -> list[_ArticleData]:
        response = await client.get(url)
        response.raise_for_status()
        check_response_size(response)

        soup = BeautifulSoup(response.text, "lxml")
        base = urlparse(url)
        articles: list[_ArticleData] = []
        seen: set[str] = set()

        for a_tag in soup.find_all("a", href=True):
            href: str = a_tag["href"].strip()
            title = a_tag.get_text(strip=True)

            if not href or not title or len(title) < 15:
                continue

            # Resolve relative URLs
            if href.startswith("/"):
                href = f"{base.scheme}://{base.netloc}{href}"
            if not href.startswith("http"):
                continue

            # Only keep article-like paths
            path = urlparse(href).path
            if not any(kw in path for kw in ["/news/", "/blog/", "/post/", "/article/"]):
                continue

            if href in seen:
                continue
            seen.add(href)

            articles.append(_ArticleData(
                url=href,
                title=title,
                content=title,
                signal_date=datetime.now(UTC),
            ))

            if len(articles) >= _MAX_ARTICLES_PER_SOURCE:
                break

        return articles

    # ------------------------------------------------------------------
    # Save (with dedup — change detection)
    # ------------------------------------------------------------------

    async def _save(
        self,
        session: AsyncSession,
        source: RadarSource,
        articles: list[_ArticleData],
    ) -> tuple[int, int]:
        inserted = skipped = 0
        now = datetime.now(UTC)

        for article in articles:
            existing = await session.scalar(
                select(RawArticle).where(RawArticle.url == article.url)
            )
            if existing:
                skipped += 1
                continue

            content_hash = hashlib.sha256(article.content.encode()).hexdigest()

            session.add(RawArticle(
                source_id=source.id,
                url=article.url,
                title=article.title,
                content=article.content,
                content_hash=content_hash,
                fetched_at=now,
                expires_at=now + timedelta(days=_RETENTION_DAYS),
            ))
            inserted += 1

        return inserted, skipped


# ------------------------------------------------------------------
# Date parsing
# ------------------------------------------------------------------

_DATE_FORMATS = [
    "%a, %d %b %Y %H:%M:%S %z",   # RFC 2822 — "Mon, 01 Jan 2024 12:00:00 +0000"
    "%a, %d %b %Y %H:%M:%S %Z",   # RFC 2822 with tz name
    "%Y-%m-%dT%H:%M:%S%z",        # ISO 8601 with offset
    "%Y-%m-%dT%H:%M:%SZ",         # ISO 8601 UTC
    "%Y-%m-%dT%H:%M:%S.%f%z",     # ISO 8601 with microseconds
]


def _parse_date(date_str: str) -> datetime:
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        except ValueError:
            continue
    return datetime.now(UTC)
