"""
Competitor Analyzer Agent — LLM classification of raw competitor content.

For each unprocessed CompetitorRawContent row (processed_at IS NULL):
  1. Truncate content to ~800 chars
  2. Call LLM: classify signal_type, sentiment, impact_level, generate summary
  3. If is_relevant=True: create CompetitorSignal
  4. Mark raw_content.processed_at = now

LLM JSON response schema:
  {
    "is_relevant": true,
    "signal_type": "product_announcement",
    "title": "...",
    "summary": "...",
    "sentiment": "positive",
    "impact_level": "Medium"
  }

Hard limit: MAX_LLM_CALLS_PER_RUN to prevent runaway costs.
"""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aiplatform.llm import get_llm_provider
from aiplatform.llm.base import Message
from aiplatform.settings import get_settings
from aiplatform.storage.competitor_models import CompetitorRawContent, CompetitorSignal

_MAX_CONTENT_CHARS = 800
_SIGNAL_EXPIRY_DAYS = 365

_VALID_SIGNAL_TYPES = {
    "product_announcement",
    "pricing_change",
    "financial_update",
    "sentiment_event",
}
_VALID_SENTIMENTS = {"positive", "neutral", "negative"}
_VALID_IMPACT_LEVELS = {"High", "Medium", "Low"}

_SYSTEM_PROMPT = """You are a competitive intelligence analyst monitoring AI platform providers.
Analyze the article or discussion and classify it as a competitive signal.

Return a JSON object with exactly these fields:
{
  "is_relevant": true or false,
  "signal_type": "product_announcement" | "pricing_change" | "financial_update" | "sentiment_event",
  "title": "short title (max 100 chars)",
  "summary": "2-3 sentence summary of the competitive implication (max 300 chars)",
  "sentiment": "positive" | "neutral" | "negative",
  "impact_level": "High" | "Medium" | "Low"
}

Rules:
- is_relevant=false if the article is not about the company's AI/tech products or strategy
- product_announcement: new model, feature, API, product launch
- pricing_change: price increase/decrease, new tier, free tier changes
- financial_update: funding, valuation, revenue, market cap news
- sentiment_event: community discussion, user feedback, controversy, adoption signal
- sentiment: from the perspective of the company's competitive position (positive = good for them)
- impact_level High: major product launch, significant price change, large funding round
- impact_level Medium: feature update, partnership, moderate community discussion
- impact_level Low: minor update, routine news, low-engagement discussion

Return ONLY the JSON object, no explanation."""


@dataclass
class CompetitorAnalyzerResult:
    articles_processed: int = 0
    signals_created: int = 0
    skipped_irrelevant: int = 0
    llm_calls: int = 0
    errors: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return (
            f"processed={self.articles_processed} "
            f"signals={self.signals_created} "
            f"irrelevant={self.skipped_irrelevant} "
            f"llm_calls={self.llm_calls} "
            f"errors={len(self.errors)}"
        )


class CompetitorAnalyzerAgent:
    async def run(self, session: AsyncSession) -> CompetitorAnalyzerResult:
        result = CompetitorAnalyzerResult()
        settings = get_settings()
        llm = get_llm_provider()
        max_calls = settings.max_llm_calls_per_run
        now = datetime.now(UTC)

        unprocessed = (
            await session.scalars(
                select(CompetitorRawContent)
                .where(CompetitorRawContent.processed_at.is_(None))
                .order_by(CompetitorRawContent.fetched_at.asc())
            )
        ).all()

        print(f"  [info] {len(unprocessed)} articles to analyze")

        for raw in unprocessed:
            if result.llm_calls >= max_calls:
                print(f"  [stop] MAX_LLM_CALLS_PER_RUN={max_calls} reached")
                break

            source_id = raw.source_id
            raw_content_id = raw.id
            company_name_hint = raw.content[:50]  # used in error messages only

                # Capture values before try block to avoid lazy-load after rollback
            article_url = raw.url
            article_title = raw.title or ""
            article_content = raw.content

            try:
                content_snippet = article_content[:_MAX_CONTENT_CHARS]
                user_message = (
                    f"Company article from: {article_url}\n"
                    f"Title: {article_title}\n\n"
                    f"Content:\n{content_snippet}"
                )

                response = await llm.complete(
                    messages=[Message(role="user", content=user_message)],
                    system_prompt=_SYSTEM_PROMPT,
                )
                result.llm_calls += 1

                parsed = _parse_llm_response(response.content)

                raw.processed_at = now
                result.articles_processed += 1

                if not parsed.get("is_relevant"):
                    result.skipped_irrelevant += 1
                    await session.flush()
                    continue

                signal_type = parsed.get("signal_type", "product_announcement")
                if signal_type not in _VALID_SIGNAL_TYPES:
                    signal_type = "product_announcement"

                sentiment = parsed.get("sentiment", "neutral")
                if sentiment not in _VALID_SENTIMENTS:
                    sentiment = "neutral"

                impact_level = parsed.get("impact_level", "Low")
                if impact_level not in _VALID_IMPACT_LEVELS:
                    impact_level = "Low"

                from aiplatform.storage.competitor_models import CompetitorSource
                source = await session.get(CompetitorSource, source_id)
                company_name = source.company_name if source else "Unknown"

                session.add(CompetitorSignal(
                    source_id=source_id,
                    raw_content_id=raw_content_id,
                    report_id=None,
                    company_name=company_name,
                    signal_type=signal_type,
                    title=str(parsed.get("title", article_title))[:500],
                    summary=str(parsed.get("summary", ""))[:1000],
                    sentiment=sentiment,
                    impact_level=impact_level,
                    url=article_url,
                    signal_date=now,
                    expires_at=now + timedelta(days=_SIGNAL_EXPIRY_DAYS),
                ))
                result.signals_created += 1
                print(
                    f"  [analyzed] {company_name}: "
                    f"type={signal_type} impact={impact_level} sentiment={sentiment}"
                )
                await session.flush()

            except Exception as exc:
                await session.rollback()
                msg = f"article {article_url[:60]}: {type(exc).__name__}: {exc}"
                result.errors.append(msg)
                print(f"  [err]   {msg}")

        return result


def _parse_llm_response(text: str) -> dict:
    text = text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to extract JSON object from response
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
        return {"is_relevant": False}
