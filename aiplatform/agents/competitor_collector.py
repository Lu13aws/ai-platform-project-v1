"""
Competitor Collector Agent — fetches signals from 4 source types per company.

Source types:
  blog      — RSS/HTML blog posts and news (stored as CompetitorRawContent for LLM analysis)
  pricing   — HTML pricing pages, hash-based change detection (direct CompetitorSignal on change)
  financial — Yahoo Finance weekly close for public companies (direct CompetitorSignal if >5% move)
  community — Hacker News Algolia search, past 7 days (stored as CompetitorRawContent)

Two-phase pattern:
  Phase 1: all HTTP fetches (no open DB session)
  Phase 2: short DB session to save results

Both phases use no-auth public APIs:
  Yahoo Finance: https://query1.finance.yahoo.com/v8/finance/chart/{TICKER}?interval=1wk&range=1mo
  HN Algolia:   https://hn.algolia.com/api/v1/search?query={company}&tags=story
"""

import hashlib
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from io import BytesIO
from typing import Any
from xml.etree import ElementTree

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aiplatform.storage.competitor_models import (
    CompetitorRawContent,
    CompetitorSignal,
    CompetitorSource,
)
from aiplatform.storage.s3 import S3Client

_REQUEST_TIMEOUT = 30.0
_MAX_ARTICLE_CONTENT = 3_000
_MAX_ARTICLES_PER_SOURCE = 15
_FINANCIAL_THRESHOLD_PCT = 5.0  # only create signal if weekly move > 5%
_RAW_CONTENT_EXPIRY_DAYS = 30
_SIGNAL_EXPIRY_DAYS = 365

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


@dataclass
class _FetchedArticle:
    source: CompetitorSource
    url: str
    title: str
    content: str
    content_hash: str


@dataclass
class _DirectSignal:
    source: CompetitorSource
    signal_type: str  # pricing_change | financial_update
    title: str
    summary: str
    sentiment: str
    impact_level: str
    url: str | None


@dataclass
class CompetitorCollectorResult:
    sources_checked: int = 0
    articles_inserted: int = 0
    articles_skipped: int = 0
    direct_signals: int = 0
    errors: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return (
            f"checked={self.sources_checked} "
            f"articles_inserted={self.articles_inserted} "
            f"articles_skipped={self.articles_skipped} "
            f"direct_signals={self.direct_signals} "
            f"errors={len(self.errors)}"
        )


class CompetitorCollectorAgent:
    async def run(self, session: AsyncSession) -> CompetitorCollectorResult:
        result = CompetitorCollectorResult()

        sources = (
            await session.scalars(
                select(CompetitorSource).where(CompetitorSource.active.is_(True))
            )
        ).all()

        # Phase 1: HTTP fetches (no open DB transaction)
        fetched_articles: list[_FetchedArticle] = []
        direct_signals: list[_DirectSignal] = []

        async with httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT,
            follow_redirects=True,
            headers=_HEADERS,
        ) as client:
            for source in sources:
                result.sources_checked += 1
                try:
                    if source.source_type == "blog":
                        articles = await _fetch_blog(client, source)
                        fetched_articles.extend(articles)
                        print(f"  [fetch] {source.name}: {len(articles)} articles")

                    elif source.source_type == "pricing":
                        signal = await _fetch_pricing(client, source)
                        if signal:
                            direct_signals.append(signal)
                            print(f"  [fetch] {source.name}: pricing CHANGED")
                        else:
                            print(f"  [fetch] {source.name}: pricing unchanged")

                    elif source.source_type == "financial":
                        signal = await _fetch_financial(client, source)
                        if signal:
                            direct_signals.append(signal)
                            print(f"  [fetch] {source.name}: {signal.title}")
                        else:
                            print(f"  [fetch] {source.name}: move < {_FINANCIAL_THRESHOLD_PCT}%, skipped")

                    elif source.source_type == "community":
                        articles = await _fetch_hn(client, source)
                        fetched_articles.extend(articles)
                        print(f"  [fetch] {source.name}: {len(articles)} HN discussions")

                except Exception as exc:
                    msg = f"{source.name}: {type(exc).__name__}: {exc}"
                    result.errors.append(msg)
                    print(f"  [err]   {msg}")

        # Phase 2: save to DB (short session)
        s3 = S3Client()
        now = datetime.now(UTC)

        # Save blog/HN articles as CompetitorRawContent (deduplicate by URL)
        for article in fetched_articles:
            source_name = article.source.name
            try:
                existing = await session.scalar(
                    select(CompetitorRawContent).where(CompetitorRawContent.url == article.url)
                )
                if existing:
                    result.articles_skipped += 1
                    continue

                session.add(CompetitorRawContent(
                    source_id=article.source.id,
                    url=article.url,
                    title=article.title,
                    content=article.content,
                    content_hash=article.content_hash,
                    fetched_at=now,
                    processed_at=None,
                    expires_at=now + timedelta(days=_RAW_CONTENT_EXPIRY_DAYS),
                ))
                await session.flush()
                result.articles_inserted += 1

            except Exception as exc:
                await session.rollback()
                msg = f"{source_name} (save article): {type(exc).__name__}: {exc}"
                result.errors.append(msg)
                print(f"  [err]   {msg}")

        # Save pricing change signals directly (upload to S3 first)
        for sig in direct_signals:
            source_name = sig.source.name
            try:
                if sig.signal_type == "pricing_change":
                    # Update the stored hash on the source
                    new_hash = sig.summary[:64] if len(sig.summary) <= 64 else hashlib.sha256(sig.summary.encode()).hexdigest()
                    sig.source.last_content_hash = new_hash

                session.add(CompetitorSignal(
                    source_id=sig.source.id,
                    raw_content_id=None,
                    report_id=None,
                    company_name=sig.source.company_name,
                    signal_type=sig.signal_type,
                    title=sig.title,
                    summary=sig.summary,
                    sentiment=sig.sentiment,
                    impact_level=sig.impact_level,
                    url=sig.url,
                    signal_date=now,
                    expires_at=now + timedelta(days=_SIGNAL_EXPIRY_DAYS),
                ))
                sig.source.last_fetched_at = now
                await session.flush()
                result.direct_signals += 1
                print(f"  [save]  {source_name}: {sig.signal_type} signal saved")

            except Exception as exc:
                await session.rollback()
                msg = f"{source_name} (save signal): {type(exc).__name__}: {exc}"
                result.errors.append(msg)
                print(f"  [err]   {msg}")

        # Update last_fetched_at for all successfully processed sources
        for source in sources:
            if source.last_fetched_at != now:
                source.last_fetched_at = now

        return result


# ── Source-type fetch helpers ──────────────────────────────────────────────────

async def _fetch_blog(
    client: httpx.AsyncClient, source: CompetitorSource
) -> list[_FetchedArticle]:
    """Fetch blog/news via RSS or HTML scraping."""
    response = await client.get(source.url)
    response.raise_for_status()

    content_type = response.headers.get("content-type", "")
    if "xml" in content_type or "rss" in content_type or source.url.endswith((".xml", ".rss")):
        return _parse_rss(response.text, source)
    return _parse_html_blog(response.text, source, str(response.url))


def _parse_rss(xml_text: str, source: CompetitorSource) -> list[_FetchedArticle]:
    articles = []
    try:
        root = ElementTree.fromstring(xml_text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        # Atom feed
        entries = root.findall("atom:entry", ns) or root.findall(".//entry")
        if entries:
            for entry in entries[:_MAX_ARTICLES_PER_SOURCE]:
                title = _xml_text(entry, ["atom:title", "title"], ns) or ""
                link_el = entry.find("atom:link", ns) or entry.find("link")
                url = (link_el.get("href") or _xml_text(entry, ["atom:link", "link"], ns) or "").strip()
                summary = _xml_text(entry, ["atom:summary", "atom:content", "summary", "content"], ns) or ""
                if url:
                    content = _clean_html(summary)[:_MAX_ARTICLE_CONTENT]
                    articles.append(_FetchedArticle(
                        source=source, url=url, title=title[:500],
                        content=content,
                        content_hash=hashlib.sha256(content.encode()).hexdigest(),
                    ))
            return articles

        # RSS 2.0
        for item in root.findall(".//item")[:_MAX_ARTICLES_PER_SOURCE]:
            title = _xml_text(item, ["title"], {}) or ""
            url = (_xml_text(item, ["link"], {}) or "").strip()
            desc = _xml_text(item, ["description", "content:encoded"], {}) or ""
            if url:
                content = _clean_html(desc)[:_MAX_ARTICLE_CONTENT]
                articles.append(_FetchedArticle(
                    source=source, url=url, title=title[:500],
                    content=content,
                    content_hash=hashlib.sha256(content.encode()).hexdigest(),
                ))
    except Exception:
        pass
    return articles


def _parse_html_blog(html: str, source: CompetitorSource, base_url: str) -> list[_FetchedArticle]:
    soup = BeautifulSoup(html, "lxml")
    articles = []
    seen: set[str] = set()

    for a in soup.find_all("a", href=True)[:100]:
        href = a["href"].strip()
        if not href.startswith("http"):
            from urllib.parse import urljoin
            href = urljoin(base_url, href)
        if href in seen:
            continue
        text = a.get_text(strip=True)
        if len(text) > 20 and _looks_like_article(href):
            seen.add(href)
            content = text[:_MAX_ARTICLE_CONTENT]
            articles.append(_FetchedArticle(
                source=source, url=href, title=text[:500],
                content=content,
                content_hash=hashlib.sha256(content.encode()).hexdigest(),
            ))
        if len(articles) >= _MAX_ARTICLES_PER_SOURCE:
            break
    return articles


async def _fetch_pricing(
    client: httpx.AsyncClient, source: CompetitorSource
) -> _DirectSignal | None:
    """Hash-compare pricing page — return signal only if content changed."""
    response = await client.get(source.url)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text()).strip()[:5_000]
    new_hash = hashlib.sha256(text.encode()).hexdigest()

    if source.last_content_hash == new_hash:
        return None

    # Content changed — store new hash and create signal
    source.last_content_hash = new_hash
    return _DirectSignal(
        source=source,
        signal_type="pricing_change",
        title=f"{source.company_name} pricing page updated",
        summary=f"The pricing page at {source.url} has changed. Review manually for new tiers, price adjustments, or removed plans.",
        sentiment="neutral",
        impact_level="Medium",
        url=source.url,
    )


async def _fetch_financial(
    client: httpx.AsyncClient, source: CompetitorSource
) -> _DirectSignal | None:
    """Fetch weekly stock data from Yahoo Finance. Only signal if move > threshold."""
    ticker = source.url.replace("yahoo://", "").strip()
    yf_url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1wk&range=1mo"

    response = await client.get(yf_url, headers={
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    })
    response.raise_for_status()

    data = response.json()
    result_data = data.get("chart", {}).get("result", [{}])[0]
    closes = result_data.get("indicators", {}).get("quote", [{}])[0].get("close", [])
    closes = [c for c in closes if c is not None]

    if len(closes) < 2:
        return None

    prev_close = closes[-2]
    last_close = closes[-1]
    if prev_close == 0:
        return None

    change_pct = ((last_close - prev_close) / prev_close) * 100

    if abs(change_pct) < _FINANCIAL_THRESHOLD_PCT:
        return None

    direction = "up" if change_pct > 0 else "down"
    sentiment = "positive" if change_pct > 0 else "negative"
    impact = "High" if abs(change_pct) > 10 else "Medium"

    return _DirectSignal(
        source=source,
        signal_type="financial_update",
        title=f"{ticker} weekly {direction} {abs(change_pct):.1f}%",
        summary=(
            f"{source.company_name} ({ticker}) moved {change_pct:+.1f}% this week "
            f"(from ${prev_close:.2f} to ${last_close:.2f}). "
            f"{'Significant upward movement may reflect positive market sentiment or news.' if change_pct > 0 else 'Significant downward movement may reflect negative sentiment or broader market pressure.'}"
        ),
        sentiment=sentiment,
        impact_level=impact,
        url=f"https://finance.yahoo.com/quote/{ticker}",
    )


async def _fetch_hn(
    client: httpx.AsyncClient, source: CompetitorSource
) -> list[_FetchedArticle]:
    """Search Hacker News via Algolia API for recent discussions about the company."""
    company = source.url.replace("hn://", "").strip()
    since = int(time.time()) - (7 * 24 * 3600)
    hn_url = (
        f"https://hn.algolia.com/api/v1/search"
        f"?query={company}&tags=story&numericFilters=created_at_i>{since}&hitsPerPage=10"
    )
    response = await client.get(hn_url, headers={"User-Agent": "AI-Platform/1.0"})
    response.raise_for_status()

    articles = []
    for hit in response.json().get("hits", []):
        url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
        title = hit.get("title") or ""
        points = hit.get("points") or 0
        num_comments = hit.get("num_comments") or 0
        content = (
            f"HN discussion: {title} | "
            f"Points: {points} | Comments: {num_comments} | "
            f"Source: {hit.get('url', 'HN submission')}"
        )
        articles.append(_FetchedArticle(
            source=source,
            url=url,
            title=title[:500],
            content=content[:_MAX_ARTICLE_CONTENT],
            content_hash=hashlib.sha256(content.encode()).hexdigest(),
        ))
    return articles


# ── Helpers ────────────────────────────────────────────────────────────────────

def _xml_text(el: Any, tags: list[str], ns: dict) -> str | None:
    for tag in tags:
        child = el.find(tag, ns) if ns else el.find(tag)
        if child is not None and child.text:
            return child.text.strip()
    return None


def _clean_html(html: str) -> str:
    if not html:
        return ""
    try:
        soup = BeautifulSoup(html, "lxml")
        return re.sub(r"\s+", " ", soup.get_text()).strip()
    except Exception:
        return re.sub(r"<[^>]+>", " ", html).strip()


def _looks_like_article(url: str) -> bool:
    patterns = ["/blog/", "/news/", "/post/", "/article/", "/press/", "/announce"]
    return any(p in url.lower() for p in patterns)
