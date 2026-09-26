"""
Cleanup Agent — enforces data retention policies.

Retention rules (from CLAUDE.md):
  raw_articles                : 30 days  (expires_at column set on insert)
  radar_reports               : 24 months (generated_at < cutoff → delete S3 + DB row)
  regulatory_reports          : 24 months (generated_at < cutoff → delete S3 JSON/HTML + DB row)
  regulatory_documents        : KEEP — version history required for historical comparison
  regulatory_changes          : KEEP — report_id set to NULL on report delete, changes retained
  competitor_raw_content      : 30 days  (expires_at column set on insert)
  competitor_signals          : 12 months (expires_at column set on insert)
  competitor_reports          : 12 months (generated_at < cutoff → delete S3 JSON/HTML + DB row)
  linkedin_posts              : 12 months (created_at < cutoff → delete DB row, no S3)

Runs monthly via EventBridge. Safe to re-run at any time.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from aiplatform.storage.competitor_models import (
    CompetitorRawContent,
    CompetitorReport,
    CompetitorSignal,
)
from aiplatform.storage.content_models import LinkedInPost
from aiplatform.storage.radar_models import RadarReport, RawArticle
from aiplatform.storage.regulatory_models import RegulatoryReport
from aiplatform.storage.s3 import S3Client

_REPORT_RETENTION_MONTHS = 24
_COMPETITOR_REPORT_RETENTION_MONTHS = 12
_LINKEDIN_POST_RETENTION_MONTHS = 12


def _cutoff(months: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=months * 30)


def _conditions() -> dict:
    """category -> (model, delete condition). Single source of truth for run() and preview()."""
    now = datetime.now(UTC)
    return {
        "raw_articles": (RawArticle, RawArticle.expires_at < now),
        "radar_reports": (RadarReport, RadarReport.generated_at < _cutoff(_REPORT_RETENTION_MONTHS)),
        "regulatory_reports": (
            RegulatoryReport,
            RegulatoryReport.generated_at < _cutoff(_REPORT_RETENTION_MONTHS),
        ),
        "competitor_raw_content": (CompetitorRawContent, CompetitorRawContent.expires_at < now),
        "competitor_signals": (CompetitorSignal, CompetitorSignal.expires_at < now),
        "competitor_reports": (
            CompetitorReport,
            CompetitorReport.generated_at < _cutoff(_COMPETITOR_REPORT_RETENTION_MONTHS),
        ),
        "linkedin_posts": (LinkedInPost, LinkedInPost.created_at < _cutoff(_LINKEDIN_POST_RETENTION_MONTHS)),
    }


@dataclass
class CleanupResult:
    articles_deleted: int = 0
    reports_deleted: int = 0
    regulatory_reports_deleted: int = 0
    competitor_raw_content_deleted: int = 0
    competitor_signals_deleted: int = 0
    competitor_reports_deleted: int = 0
    linkedin_posts_deleted: int = 0
    s3_objects_deleted: int = 0
    errors: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []

    def __str__(self) -> str:
        return (
            f"articles_deleted={self.articles_deleted} "
            f"reports_deleted={self.reports_deleted} "
            f"regulatory_reports_deleted={self.regulatory_reports_deleted} "
            f"competitor_raw_deleted={self.competitor_raw_content_deleted} "
            f"competitor_signals_deleted={self.competitor_signals_deleted} "
            f"competitor_reports_deleted={self.competitor_reports_deleted} "
            f"linkedin_posts_deleted={self.linkedin_posts_deleted} "
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
        await self._delete_old_regulatory_reports(session, result)
        await self._delete_expired_competitor_raw_content(session, result)
        await self._delete_expired_competitor_signals(session, result)
        await self._delete_old_competitor_reports(session, result)
        await self._delete_old_linkedin_posts(session, result)

        return result

    async def preview(self, session: AsyncSession) -> dict[str, dict[str, int]]:
        """Read-only: how many rows run() would delete right now (same conditions), per category."""
        await session.execute(text("SET TRANSACTION READ ONLY"))
        counts = {}
        for name, (model, condition) in _conditions().items():
            would_delete = await session.scalar(select(func.count()).select_from(model).where(condition))
            total = await session.scalar(select(func.count()).select_from(model))
            counts[name] = {"would_delete": would_delete, "total": total}
        return counts

    async def _delete_expired_articles(self, session: AsyncSession, result: CleanupResult) -> None:
        stmt = delete(RawArticle).where(_conditions()["raw_articles"][1])
        db_result = await session.execute(stmt)
        result.articles_deleted = db_result.rowcount
        print(f"  [cleanup] raw_articles deleted: {result.articles_deleted}")

    async def _delete_old_reports(self, session: AsyncSession, result: CleanupResult) -> None:
        old_reports = (
            await session.scalars(select(RadarReport).where(_conditions()["radar_reports"][1]))
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

    async def _delete_old_regulatory_reports(
        self, session: AsyncSession, result: CleanupResult
    ) -> None:
        """Delete regulatory_reports older than 24 months + their S3 JSON/HTML files.

        regulatory_changes linked to deleted reports have report_id SET NULL — they
        are retained permanently for historical reference (per CLAUDE.md retention rules).
        regulatory_documents (version history) are never deleted automatically.
        """
        old_reports = (
            await session.scalars(
                select(RegulatoryReport).where(_conditions()["regulatory_reports"][1])
            )
        ).all()

        print(f"  [cleanup] old regulatory_reports found: {len(old_reports)}")

        for report in old_reports:
            for key in [k for k in [report.s3_key_json, report.s3_key_html] if k]:
                try:
                    await self._s3.delete(key)
                    result.s3_objects_deleted += 1
                    print(f"  [cleanup] s3 deleted: {key}")
                except Exception as exc:
                    result.errors.append(f"s3 delete {key}: {exc}")
                    print(f"  [cleanup] s3 delete failed: {key}: {exc}")

            await session.delete(report)
            result.regulatory_reports_deleted += 1

        print(f"  [cleanup] regulatory_reports deleted: {result.regulatory_reports_deleted}")


    async def _delete_expired_competitor_raw_content(
        self, session: AsyncSession, result: CleanupResult
    ) -> None:
        stmt = delete(CompetitorRawContent).where(_conditions()["competitor_raw_content"][1])
        db_result = await session.execute(stmt)
        result.competitor_raw_content_deleted = db_result.rowcount
        print(f"  [cleanup] competitor_raw_content deleted: {result.competitor_raw_content_deleted}")

    async def _delete_expired_competitor_signals(
        self, session: AsyncSession, result: CleanupResult
    ) -> None:
        stmt = delete(CompetitorSignal).where(_conditions()["competitor_signals"][1])
        db_result = await session.execute(stmt)
        result.competitor_signals_deleted = db_result.rowcount
        print(f"  [cleanup] competitor_signals deleted: {result.competitor_signals_deleted}")

    async def _delete_old_competitor_reports(
        self, session: AsyncSession, result: CleanupResult
    ) -> None:
        old_reports = (
            await session.scalars(
                select(CompetitorReport).where(_conditions()["competitor_reports"][1])
            )
        ).all()

        print(f"  [cleanup] old competitor_reports found: {len(old_reports)}")

        for report in old_reports:
            for key in [report.s3_key_json, report.s3_key_html]:
                if not key:
                    continue
                try:
                    await self._s3.delete(key)
                    result.s3_objects_deleted += 1
                    print(f"  [cleanup] s3 deleted: {key}")
                except Exception as exc:
                    result.errors.append(f"s3 delete {key}: {exc}")
                    print(f"  [cleanup] s3 delete failed: {key}: {exc}")

            await session.delete(report)
            result.competitor_reports_deleted += 1

        print(f"  [cleanup] competitor_reports deleted: {result.competitor_reports_deleted}")


    async def _delete_old_linkedin_posts(
        self, session: AsyncSession, result: CleanupResult
    ) -> None:
        stmt = delete(LinkedInPost).where(_conditions()["linkedin_posts"][1])
        db_result = await session.execute(stmt)
        result.linkedin_posts_deleted = db_result.rowcount
        print(f"  [cleanup] linkedin_posts deleted: {result.linkedin_posts_deleted}")


def _derive_s3_keys(json_key: str) -> list[str]:
    """Given the JSON report key, return both JSON and HTML keys."""
    html_key = json_key.replace(".json", ".html")
    return [json_key, html_key]
