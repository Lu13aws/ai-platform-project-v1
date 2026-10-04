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
from typing import Any

import httpx
from bs4 import BeautifulSoup
from defusedxml import ElementTree
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aiplatform.agents.fetch_utils import check_response_size
from aiplatform.storage.competitor_models import (
    CompetitorRawContent,
    CompetitorSignal,
    CompetitorSource,
)

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
                # NOTE: `source.last_content_hash` for pricing_change signals is already
                # set correctly inside `_fetch_pricing` (the price-token fingerprint hash).
                # Do NOT recompute/overwrite it here from `sig.summary` — the summary text
                # is a fixed template per source (same url/company_name every run), so
                # hashing it produced a near-constant value that permanently desynced the
                # stored hash from the real page fingerprint, guaranteeing a mismatch (and
                # therefore a signal) on every subsequent run regardless of actual change.
                # This was a second, compounding bug behind the "fires every single week"
                # behaviour — see competitor_collector.py::_fetch_pricing docstring.
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
    check_response_size(response)

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
    """Fingerprint-compare a pricing page's price/plan tokens — return a signal only if
    the set of detected prices actually changed, not on any unrelated page edit.

    Previously this hashed ALL visible page text (ads, timestamps, cookie banners,
    reworded marketing copy included), which changed on essentially every fetch and
    fired a false `pricing_change` signal every week for every source (confirmed in
    production: 78/78 company-weeks). Now we extract only currency-amount tokens
    (optionally paired with a billing-period suffix, e.g. "$29/mo", "€49/yr") and hash
    a normalized, deduped, sorted representation of those tokens instead. Unrelated
    page changes no longer affect the fingerprint; only a change in the actual set of
    displayed prices does.
    """
    response = await client.get(source.url)
    response.raise_for_status()
    check_response_size(response)

    soup = BeautifulSoup(response.text, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text()).strip()

    price_tokens = _extract_price_tokens(text)

    if not price_tokens:
        # No price-looking tokens found anywhere on the page at all — most likely a
        # JS-rendered pricing page whose static HTML carries no visible price text.
        # Deliberately do NOT fall back to hashing the whole page (that's the exact
        # behaviour being removed) and do NOT emit a signal: a page with zero
        # extractable prices gives us nothing reliable to compare. We also leave
        # `last_content_hash` untouched so that a future run which *does* find tokens
        # is compared against the last real price fingerprint, not clobbered here.
        print(f"  [pricing] {source.name}: no price tokens found, skipping change detection")
        return None

    fingerprint = "|".join(price_tokens)
    new_hash = hashlib.sha256(fingerprint.encode()).hexdigest()

    if source.last_content_hash == new_hash:
        return None

    # Price fingerprint changed — store new hash and create signal
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


# ── Pricing token extraction ────────────────────────────────────────────────────

_CURRENCY_SYMBOLS = "$€£"

# Matches a currency amount (e.g. "$29", "€1,299.00", "£9.99") optionally followed
# by a billing-period suffix (e.g. "/mo", "/month", "per year", "monthly").
_PRICE_TOKEN_RE = re.compile(
    rf"(?P<currency>[{_CURRENCY_SYMBOLS}])\s?"
    r"(?P<amount>\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)"
    r"(?P<period>\s?/\s?[a-zA-Z]+|\s+per\s+[a-zA-Z]+|\s*(?:monthly|annually|yearly|biweekly))?",
    re.IGNORECASE,
)

# Canonicalizes the many ways a billing period is written to one short code, so
# "$29/mo", "$29 per month", and "$29 monthly" all normalize to the same token.
_PERIOD_ALIASES = {
    "mo": "mo", "month": "mo", "months": "mo", "monthly": "mo",
    "yr": "yr", "year": "yr", "years": "yr", "yearly": "yr", "annually": "yr", "annum": "yr",
    "wk": "wk", "week": "wk", "weekly": "wk",
    "seat": "seat", "seats": "seat",
    "user": "user", "users": "user",
}


def _normalize_period(raw: str | None) -> str:
    if not raw:
        return ""
    words = re.findall(r"[a-zA-Z]+", raw)
    if not words:
        return ""
    # The unit word is always last ("/mo" -> "mo", "per month" -> "month").
    canon = _PERIOD_ALIASES.get(words[-1].lower())
    return f"/{canon}" if canon else ""


def _normalize_amount(raw: str) -> str:
    """Normalize "1,299.00" / "29" / "29.00" / "9.99" to a canonical decimal string
    (no thousands separator, no trailing zero padding) so formatting-only changes
    don't change the fingerprint."""
    value = float(raw.replace(",", ""))
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text or "0"


def _extract_price_tokens(text: str) -> list[str]:
    """Extract a normalized, deduped, sorted list of price tokens from page text.

    Sorting + deduping means unrelated reordering of page content (e.g. tier cards
    rendered in a different DOM order) does not change the fingerprint — only the
    actual *set* of distinct prices shown on the page matters.
    """
    tokens: set[str] = set()
    for match in _PRICE_TOKEN_RE.finditer(text):
        currency = match.group("currency")
        amount = _normalize_amount(match.group("amount"))
        period = _normalize_period(match.group("period"))
        tokens.add(f"{currency}{amount}{period}")
    return sorted(tokens)


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
