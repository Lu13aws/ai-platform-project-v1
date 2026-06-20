"""
ContentCreatorAgent — generates LinkedIn posts from radar + competitor signal data.

Rotation logic (persisted in S3 content/rotation_state.json):
  - Domain alternates by ISO week number: odd=competitor, even=technology
  - Angle rotates in 4-week cycle: product → pricing → sentiment → financial
  - Company selected round-robin from DB (CompetitorSource or RadarEntry)
"""

import json
import uuid
from datetime import UTC, datetime

import boto3
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aiplatform.llm import Message, get_llm_provider
from aiplatform.settings import settings
from aiplatform.storage.competitor_models import CompetitorSignal, CompetitorSource
from aiplatform.storage.content_models import LinkedInPost
from aiplatform.storage.radar_models import RadarEntry, RadarSignal

_ANGLES = ["product", "pricing", "sentiment", "financial"]

_ANGLE_LABELS = {
    "competitor": {
        "product": "product announcements and new features",
        "pricing": "pricing changes and competitive positioning",
        "sentiment": "community sentiment and developer perception",
        "financial": "financial results and market performance",
    },
    "technology": {
        "product": "newly adopted technologies and tooling",
        "pricing": "cost and value positioning of technology choices",
        "sentiment": "developer adoption trends and community feedback",
        "financial": "vendor investment signals and market momentum",
    },
}

_SYSTEM_PROMPT = """\
You are a professional LinkedIn content writer for a senior Data Engineer and Solutions Architect.

Write ONE LinkedIn post based on the signal data provided. Follow these rules exactly:

STRUCTURE:
1. Hook (1 sentence) — attention-grabbing opening, no generic phrases
2. Context (2-3 sentences) — what's happening and why it matters
3. Key insights (3-4 bullet points starting with •)
4. Personal takeaway (1-2 sentences, first-person, learning-focused)
5. Closing CTA (1 sentence) — question or invitation to discuss

RULES:
- Length: 200-400 words
- Tone: professional, approachable, first-person ("I've been tracking...", "What caught my attention...")
- Emojis: max 4, placed naturally (not at every bullet)
- Hashtags: 5-8, at the end only
- Do NOT use: "In today's fast-paced world", "Game-changer", "Revolutionizing", "Delve into"
- Do NOT fabricate data not present in the signals
- Write as if YOU observed these trends through your monitoring pipeline

Return ONLY the post text — no JSON wrapper, no preamble.
"""


def _rotation_key() -> str:
    return f"content/rotation_state.json"


def _load_rotation_state(s3_client) -> dict:
    try:
        resp = s3_client.get_object(Bucket=settings.s3_bucket_name, Key=_rotation_key())
        return json.loads(resp["Body"].read())
    except s3_client.exceptions.NoSuchKey:
        return {}
    except Exception:
        return {}


def _save_rotation_state(s3_client, state: dict) -> None:
    s3_client.put_object(
        Bucket=settings.s3_bucket_name,
        Key=_rotation_key(),
        Body=json.dumps(state, indent=2).encode(),
        ContentType="application/json",
    )


def _next_angle(state: dict) -> str:
    last = state.get("last_angle", _ANGLES[-1])
    idx = _ANGLES.index(last) if last in _ANGLES else -1
    return _ANGLES[(idx + 1) % len(_ANGLES)]


def _current_domain() -> str:
    week = datetime.now(UTC).isocalendar()[1]
    return "competitor" if week % 2 == 1 else "technology"


class ContentCreatorAgent:
    def __init__(self) -> None:
        self._s3 = boto3.client("s3", region_name=settings.aws_region)

    async def run(self, session: AsyncSession) -> LinkedInPost:
        state = _load_rotation_state(self._s3)
        domain = _current_domain()
        angle = _next_angle(state)

        print(f"[content_creator] domain={domain} angle={angle}")

        if domain == "competitor":
            company, signals_text = await self._competitor_signals(session, angle, state)
        else:
            company, signals_text = await self._radar_signals(session, angle, state)

        print(f"[content_creator] company={company}, generating post...")

        provider = get_llm_provider()
        user_msg = (
            f"Company/Technology focus: {company}\n"
            f"Topic angle: {_ANGLE_LABELS[domain][angle]}\n"
            f"Domain: {domain}\n\n"
            f"--- Signal data ---\n{signals_text}"
        )
        response = await provider.complete(
            [Message(role="user", content=user_msg)],
            system_prompt=_SYSTEM_PROMPT,
        )
        post_content = response.content.strip()
        print(f"[content_creator] post generated ({len(post_content)} chars, {response.input_tokens}in/{response.output_tokens}out tokens)")

        post = LinkedInPost(
            id=uuid.uuid4(),
            domain=domain,
            angle=angle,
            company=company,
            content=post_content,
        )
        session.add(post)
        await session.flush()

        # Update rotation state
        state["last_angle"] = angle
        state["last_domain"] = domain
        state[f"last_company_{domain}"] = company
        state["last_run"] = datetime.now(UTC).isoformat()
        _save_rotation_state(self._s3, state)

        print(f"[content_creator] post saved: {post.id}")
        return post

    async def _competitor_signals(self, session: AsyncSession, angle: str, state: dict) -> tuple[str, str]:
        # Pick next company round-robin from CompetitorSource
        companies_result = await session.execute(
            select(CompetitorSource.company_name).distinct().order_by(CompetitorSource.company_name)
        )
        companies = [r[0] for r in companies_result.all()]
        if not companies:
            company = "Competitor"
        else:
            last = state.get("last_company_competitor", "")
            idx = companies.index(last) if last in companies else -1
            company = companies[(idx + 1) % len(companies)]

        # Map angle to signal_type
        type_map = {
            "product": "product_announcement",
            "pricing": "pricing_change",
            "financial": "financial_update",
            "sentiment": "sentiment_event",
        }
        signal_type = type_map.get(angle, "product_announcement")

        signals = await session.execute(
            select(CompetitorSignal)
            .where(CompetitorSignal.company_name == company)
            .where(CompetitorSignal.signal_type == signal_type)
            .order_by(CompetitorSignal.signal_date.desc())
            .limit(8)
        )
        rows = signals.scalars().all()

        if not rows:
            # Fallback: any signal for this company
            signals = await session.execute(
                select(CompetitorSignal)
                .where(CompetitorSignal.company_name == company)
                .order_by(CompetitorSignal.signal_date.desc())
                .limit(8)
            )
            rows = signals.scalars().all()

        text = "\n\n".join(
            f"[{r.signal_type}] {r.title}\n{r.summary}\nSentiment: {r.sentiment} | Impact: {r.impact_level}"
            + (f"\nSource: {r.url}" if r.url else "")
            for r in rows
        ) or "No recent signals found for this company."

        return company, text

    async def _radar_signals(self, session: AsyncSession, angle: str, state: dict) -> tuple[str, str]:
        # Pick next vendor round-robin from RadarEntry
        vendors_result = await session.execute(
            select(RadarEntry.vendor).distinct().order_by(RadarEntry.vendor)
        )
        vendors = [r[0] for r in vendors_result.all()]
        if not vendors:
            vendor = "Technology"
        else:
            last = state.get("last_company_technology", "")
            idx = vendors.index(last) if last in vendors else -1
            vendor = vendors[(idx + 1) % len(vendors)]

        entries = await session.execute(
            select(RadarEntry)
            .where(RadarEntry.vendor == vendor)
            .order_by(RadarEntry.last_updated_at.desc())
            .limit(5)
        )
        entry_rows = entries.scalars().all()

        signals = await session.execute(
            select(RadarSignal)
            .where(RadarSignal.vendor == vendor)
            .order_by(RadarSignal.signal_date.desc())
            .limit(8)
        )
        signal_rows = signals.scalars().all()

        entries_text = "\n".join(
            f"- {e.technology_name} [{e.category}] trend={e.trend}: {e.summary}"
            for e in entry_rows
        ) or "No radar entries found."

        signals_text = "\n".join(
            f"- [{r.category}] {r.signal_text[:300]}"
            for r in signal_rows
        ) or "No recent signals."

        text = f"Radar Entries:\n{entries_text}\n\nRecent Signals:\n{signals_text}"
        return vendor, text
