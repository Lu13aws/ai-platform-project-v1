"""
Analysis Agent — reads unprocessed raw_articles, calls LLM to classify each one,
writes radar_signals, and upserts radar_entries.

LLM call per article: extracts technology name, vendor, radar category
(Adopt/Trial/Assess/Hold), a signal summary, and a confidence score.

Cost control: MAX_LLM_CALLS_PER_RUN setting hard-stops the agent.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aiplatform.llm import get_llm_provider
from aiplatform.llm.base import Message
from aiplatform.settings import settings
from aiplatform.storage.radar_models import RadarEntry, RadarSignal, RawArticle

_VALID_CATEGORIES = {"Adopt", "Trial", "Assess", "Hold"}
_VALID_TRENDS = {"up", "stable", "down"}
_CATEGORY_RANK = {"Adopt": 3, "Trial": 2, "Assess": 1, "Hold": 0}

_SYSTEM_PROMPT = """\
You are a technology radar analyst. Your job is to read technology news articles
and extract structured signals about specific technologies or products.

A technology radar classifies technologies into four categories:
- Adopt:  Mature and recommended for production use.
- Trial:  Worth pursuing; ready for enterprise projects with manageable risk.
- Assess: Promising; worth exploring with low-risk pilots.
- Hold:   Not recommended for new projects; proceed with caution or avoid.

Always respond with a single valid JSON object and nothing else."""

_USER_PROMPT = """\
Analyze this article and extract a technology signal.

Source: {vendor}
Title: {title}
Content: {content}

Respond with this exact JSON structure:
{{
  "technology_name": "specific technology, product, or service name",
  "vendor": "company or organization name",
  "category": "Adopt or Trial or Assess or Hold",
  "sentiment": "positive or neutral or negative",
  "signal_text": "1-2 sentences summarizing what this reveals about the technology",
  "confidence_score": 0.85,
  "is_relevant": true
}}

Set is_relevant to false if the article is not about a specific technology
(e.g. purely a job posting, generic company news, or marketing with no technical signal).
sentiment reflects the article's tone toward the technology.
confidence_score must be between 0.0 and 1.0."""


@dataclass
class AnalysisResult:
    articles_processed: int = 0
    signals_created: int = 0
    entries_upserted: int = 0
    articles_irrelevant: int = 0
    llm_calls: int = 0
    errors: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return (
            f"processed={self.articles_processed} "
            f"signals={self.signals_created} "
            f"entries={self.entries_upserted} "
            f"irrelevant={self.articles_irrelevant} "
            f"llm_calls={self.llm_calls} "
            f"errors={len(self.errors)}"
        )


class AnalyzerAgent:
    async def run(self, session: AsyncSession) -> AnalysisResult:
        result = AnalysisResult()
        provider = get_llm_provider()

        unprocessed = (
            await session.scalars(
                select(RawArticle)
                .where(RawArticle.processed_at.is_(None))
                .order_by(RawArticle.fetched_at.asc())
            )
        ).all()

        print(f"  [info] {len(unprocessed)} unprocessed articles")

        for article in unprocessed:
            if result.llm_calls >= settings.max_llm_calls_per_run:
                print(f"  [stop] LLM call limit reached ({settings.max_llm_calls_per_run})")
                break

            try:
                parsed = await self._classify(provider, article)
                result.llm_calls += 1

                if not parsed.get("is_relevant", True):
                    result.articles_irrelevant += 1
                else:
                    await self._save_signal(session, article, parsed)
                    result.signals_created += 1
                    upserted = await self._upsert_entry(session, parsed)
                    if upserted:
                        result.entries_upserted += 1

                article.processed_at = datetime.now(UTC)
                result.articles_processed += 1

            except Exception as exc:
                msg = f"article {article.id}: {type(exc).__name__}: {exc}"
                result.errors.append(msg)
                print(f"  [err] {msg}")

        return result

    # ------------------------------------------------------------------
    # LLM classification
    # ------------------------------------------------------------------

    async def _classify(self, provider, article: RawArticle) -> dict:
        # Truncate content to keep token usage low (~800 chars is enough context)
        content = (article.content or "")[:800]

        # Get source name from the relationship or fall back to URL hostname
        from urllib.parse import urlparse
        vendor_hint = urlparse(article.url).netloc.replace("www.", "")

        prompt = _USER_PROMPT.format(
            vendor=vendor_hint,
            title=article.title or "",
            content=content,
        )

        response = await provider.complete(
            messages=[Message(role="user", content=prompt)],
            system_prompt=_SYSTEM_PROMPT,
        )

        return _parse_json(response.content)

    # ------------------------------------------------------------------
    # Persist
    # ------------------------------------------------------------------

    async def _save_signal(
        self, session: AsyncSession, article: RawArticle, data: dict
    ) -> None:
        category = _validated_category(data.get("category", "Assess"))
        confidence = float(data.get("confidence_score", 0.5))
        confidence = max(0.0, min(1.0, confidence))

        sentiment = str(data.get("sentiment", "neutral")).lower()
        if sentiment not in {"positive", "neutral", "negative"}:
            sentiment = "neutral"

        session.add(RadarSignal(
            source_id=article.source_id,
            article_id=article.id,
            technology_name=str(data.get("technology_name", "Unknown"))[:256],
            vendor=str(data.get("vendor", "Unknown"))[:128],
            category=category,
            sentiment=sentiment,
            signal_text=str(data.get("signal_text", ""))[:2000],
            confidence_score=confidence,
            signal_date=article.fetched_at,
        ))

    async def _upsert_entry(self, session: AsyncSession, data: dict) -> bool:
        tech_name = str(data.get("technology_name", "Unknown"))[:256]
        vendor = str(data.get("vendor", "Unknown"))[:128]
        new_category = _validated_category(data.get("category", "Assess"))
        signal_text = str(data.get("signal_text", ""))

        existing = await session.scalar(
            select(RadarEntry).where(
                RadarEntry.technology_name == tech_name,
                RadarEntry.vendor == vendor,
            )
        )

        if existing:
            trend = _calculate_trend(existing.category, new_category)
            existing.category = new_category
            existing.summary = signal_text
            existing.trend = trend
            existing.signal_count += 1
            existing.last_updated_at = datetime.now(UTC)
            return False  # updated, not newly inserted
        else:
            session.add(RadarEntry(
                technology_name=tech_name,
                vendor=vendor,
                category=new_category,
                summary=signal_text,
                trend="stable",
                signal_count=1,
                last_updated_at=datetime.now(UTC),
            ))
            return True  # newly inserted


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _validated_category(value: str) -> str:
    cat = str(value).strip().title()
    return cat if cat in _VALID_CATEGORIES else "Assess"


def _calculate_trend(old_category: str, new_category: str) -> str:
    old_rank = _CATEGORY_RANK.get(old_category, 1)
    new_rank = _CATEGORY_RANK.get(new_category, 1)
    if new_rank > old_rank:
        return "up"
    if new_rank < old_rank:
        return "down"
    return "stable"


def _parse_json(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # LLM sometimes wraps JSON in markdown code fences — strip and retry
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse JSON from LLM response: {text[:200]}")
