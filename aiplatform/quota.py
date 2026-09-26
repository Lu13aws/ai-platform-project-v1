"""Daily cap on LLM-backed requests served to unauthenticated public endpoints."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

import boto3
from botocore.config import Config
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from aiplatform.retrieval.embedder import CostLimitExceeded
from aiplatform.settings import settings
from aiplatform.storage.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

PUBLIC_QUERY_SCOPE = "public_query"
NOTICE_SCOPE = "public_query_limit_notice"

# One atomic statement: increments only while below the limit; no row back = limit reached.
_CONSUME_SQL = text(
    """
    INSERT INTO usage_counters (scope, day, count) VALUES (:scope, :day, 1)
    ON CONFLICT (scope, day) DO UPDATE SET count = usage_counters.count + 1
    WHERE usage_counters.count < :limit
    RETURNING count
    """
)

# Atomic "first one of the day wins": returns a row only for the very first caller.
_CLAIM_NOTICE_SQL = text(
    """
    INSERT INTO usage_counters (scope, day, count) VALUES (:scope, :day, 1)
    ON CONFLICT (scope, day) DO NOTHING
    RETURNING count
    """
)
_RELEASE_NOTICE_SQL = text("DELETE FROM usage_counters WHERE scope = :scope AND day = :day")


class DailyQuotaExceeded(CostLimitExceeded):
    def __init__(self, limit: int, retry_after: int) -> None:
        self.limit = limit
        self.retry_after = retry_after
        hours, minutes = divmod(retry_after // 60, 60)
        super().__init__(
            f"The public demo has reached its daily limit of {limit} AI questions "
            "(a cost cap for this portfolio project). The counter resets at 00:00 UTC, "
            f"please try again in about {hours} h {minutes} min."
        )


def _seconds_until_utc_midnight(now: datetime) -> int:
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return int((midnight - now).total_seconds())


def _publish_limit_notice(limit: int, now: datetime) -> None:
    # Short timeouts, no retries: the caller must not hang on a slow SNS.
    sns = boto3.client(
        "sns",
        region_name=settings.aws_region,
        config=Config(connect_timeout=3, read_timeout=3, retries={"max_attempts": 1}),
    )
    sns.publish(
        TopicArn=settings.sns_topic_arn,
        Subject="[AI Platform] Public demo daily limit reached",
        Message=(
            f"The public demo hit its daily limit of {limit} AI questions at "
            f"{now:%H:%M} UTC on {now:%Y-%m-%d}. Visitors get HTTP 429 until 00:00 UTC.\n\n"
            "Legitimate traffic or abuse? Check the CloudWatch logs of ai-platform-rag-demo.\n"
            "To reopen today, raise PUBLIC_DAILY_LLM_LIMIT on the Lambda "
            "(scripts/deploy_lambda.py)."
        ),
    )


async def _notify_limit_reached_once(now: datetime, limit: int) -> None:
    """One SNS message per UTC day, when the cap is first hit. Never raises."""
    params = {"scope": NOTICE_SCOPE, "day": now.date()}
    try:
        async with AsyncSessionLocal() as session, session.begin():
            claimed = (await session.execute(_CLAIM_NOTICE_SQL, params)).first() is not None
        if not claimed:
            return
        if not settings.sns_topic_arn:
            logger.warning("Daily limit reached but SNS_TOPIC_ARN is not set; no notification sent")
            return
        try:
            await asyncio.to_thread(_publish_limit_notice, limit, now)
        except Exception:
            # Release the claim so the next rejected request retries the notification.
            async with AsyncSessionLocal() as session, session.begin():
                await session.execute(_RELEASE_NOTICE_SQL, params)
            raise
    except Exception:
        logger.exception("Could not send daily-limit notification")


async def consume_public_query_quota() -> None:
    """Count one public LLM request; raise DailyQuotaExceeded once today's cap is used up."""
    now = datetime.now(UTC)
    limit = settings.public_daily_llm_limit
    params = {"scope": PUBLIC_QUERY_SCOPE, "day": now.date(), "limit": limit}
    async with AsyncSessionLocal() as session, session.begin():  # own transaction, commits at once
        row = (await session.execute(_CONSUME_SQL, params)).first()
    if row is None:
        await _notify_limit_reached_once(now, limit)
        raise DailyQuotaExceeded(limit, _seconds_until_utc_midnight(now))


def register_quota_handler(app: FastAPI) -> None:
    @app.exception_handler(DailyQuotaExceeded)
    async def _handle(_request: Request, exc: DailyQuotaExceeded) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={"detail": str(exc)},
            headers={"Retry-After": str(exc.retry_after)},
        )
