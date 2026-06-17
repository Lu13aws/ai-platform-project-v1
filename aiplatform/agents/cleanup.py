"""
Cleanup Agent — enforces data retention policies.

Retention rules (from CLAUDE.md):
  raw_articles   : 30 days  (expires_at column set on insert)
  radar_reports  : 24 months (generated_at < cutoff → delete S3 + DB row)

Runs monthly via EventBridge. Safe to re-run at any time.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from aiplatform.storage.radar_models import RadarReport, RawArticle
from aiplatform.storage.s3 import S3Client

_REPORT_RETENTION_MONTHS = 24


@dataclass
class CleanupResult:
    articles_deleted: int = 0
    reports_deleted: int = 0
    s3_objects_deleted: int = 0
    errors: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []

    def __str__(self) -> str:
        return (
            f"articles_deleted={self.articles_deleted} "
            f"reports_deleted={self.reports_deleted} "
            f"s3_deleted={self.s3_objects_deleted} "
            f"errors={len(self.errors)}"
        )


class CleanupAgent:
    def __init__(self, s3: S3Client | None = None) -> None:
        self._s3 = s3 or S3Client()

    async def run(self, session: AsyncSession) -> CleanupResult:
        result = CleanupResult()

        await self._delete_expired_articles(session, result)
        await self._delete_old_reports(session, result)

        return result

    async def _delete_expired_articles(self, session: AsyncSession, result: CleanupResult) -> None:
        now = datetime.now(UTC)
        stmt = delete(RawArticle).where(RawArticle.expires_at < now)
        db_result = await session.execute(stmt)
        result.articles_deleted = db_result.rowcount
        print(f"  [cleanup] raw_articles deleted: {result.articles_deleted}")

    async def _delete_old_reports(self, session: AsyncSession, result: CleanupResult) -> None:
        cutoff = datetime.now(UTC) - timedelta(days=_REPORT_RETENTION_MONTHS * 30)

        old_reports = (
            await session.scalars(
                select(RadarReport).where(RadarReport.generated_at < cutoff)
            )
        ).all()

        print(f"  [cleanup] old radar_reports found: {len(old_reports)}")

        for report in old_reports:
            # Delete S3 objects (JSON + HTML share the same key prefix)
            if report.s3_key:
                for key in _derive_s3_keys(report.s3_key):
                    try:
                        await self._s3.delete(key)
                        result.s3_objects_deleted += 1
                        print(f"  [cleanup] s3 deleted: {key}")
                    except Exception as exc:
                        result.errors.append(f"s3 delete {key}: {exc}")
                        print(f"  [cleanup] s3 delete failed: {key}: {exc}")

            await session.delete(report)
            result.reports_deleted += 1

        print(f"  [cleanup] radar_reports deleted: {result.reports_deleted}")


def _derive_s3_keys(json_key: str) -> list[str]:
    """Given the JSON report key, return both JSON and HTML keys."""
    html_key = json_key.replace(".json", ".html")
    return [json_key, html_key]
