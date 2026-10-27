"""
Radar history — keeps the category of every radar entry per pipeline run.

radar_entries only holds this week and last week (category / previous_category), so movement
over months is lost after two runs. Phase 7 needs that history; it cannot be collected later.

Two writers, one table (radar_entry_history, one row per technology + vendor + run_date):
  - record_run()  — pipeline phase after change detection: copies radar_entries as of today.
                    A rerun on the same day overwrites that day's rows.
  - backfill()    — one-off: rebuilds past runs from the radar report JSONs on S3.
                    Never overwrites a row that already exists.
"""

import json
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from aiplatform.storage.radar_models import RadarEntryHistory, RadarReport
from aiplatform.storage.s3 import S3Client

_RECORD_SQL = text(
    """
    INSERT INTO radar_entry_history
        (id, run_date, technology_name, vendor, category, previous_category,
         trend, signal_count, origin, recorded_at)
    SELECT gen_random_uuid(), :run_date, technology_name, vendor, category, previous_category,
           trend, signal_count, 'pipeline', NOW()
    FROM radar_entries
    ON CONFLICT (technology_name, vendor, run_date) DO UPDATE SET
        category = EXCLUDED.category,
        previous_category = EXCLUDED.previous_category,
        trend = EXCLUDED.trend,
        signal_count = EXCLUDED.signal_count,
        origin = EXCLUDED.origin,
        recorded_at = EXCLUDED.recorded_at
    """
)


async def ensure_table(session: AsyncSession) -> None:
    """Create radar_entry_history if missing (no alembic in the Lambda image)."""
    conn = await session.connection()
    await conn.run_sync(lambda sync_conn: RadarEntryHistory.__table__.create(sync_conn, checkfirst=True))


async def record_run(session: AsyncSession, run_date: date) -> int:
    await ensure_table(session)
    result = await session.execute(_RECORD_SQL, {"run_date": run_date})
    print(f"  [history] {result.rowcount} entries recorded for {run_date}")
    return result.rowcount


def rows_from_reports(reports: list[dict]) -> list[dict]:
    """Turn radar report JSONs into history rows, oldest first.

    previous_category is the category in the preceding report (None the first time an entry
    appears). Several reports on one day collapse into the last one, like a same-day rerun.
    """
    by_date: dict[date, dict] = {}
    for report in sorted(reports, key=lambda r: r["generated_at"]):
        by_date[datetime.fromisoformat(report["generated_at"]).date()] = report

    rows: list[dict] = []
    last_seen: dict[tuple[str, str], str] = {}
    for run_date, report in sorted(by_date.items()):
        for entries in report.get("entries", {}).values():
            for e in entries:
                key = (e["technology_name"], e["vendor"])
                rows.append({
                    "run_date": run_date,
                    "technology_name": e["technology_name"],
                    "vendor": e["vendor"],
                    "category": e["category"],
                    "previous_category": last_seen.get(key),
                    "trend": e.get("trend"),
                    "signal_count": e.get("signal_count"),
                    "origin": "backfill",
                })
                last_seen[key] = e["category"]
    return rows


@dataclass
class BackfillResult:
    reports_read: int = 0
    rows_built: int = 0
    rows_inserted: int = 0
    run_dates: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "reports_read": self.reports_read,
            "rows_built": self.rows_built,
            "rows_inserted": self.rows_inserted,
            "first_run_date": self.run_dates[0] if self.run_dates else None,
            "last_run_date": self.run_dates[-1] if self.run_dates else None,
            "run_dates": len(self.run_dates),
            "errors": self.errors,
        }


async def backfill(session: AsyncSession, s3: S3Client | None = None, dry_run: bool = True) -> BackfillResult:
    """Rebuild history from every radar report still on S3 (24-month retention)."""
    s3 = s3 or S3Client()
    result = BackfillResult()

    keys = (await session.scalars(select(RadarReport.s3_key).where(RadarReport.s3_key.is_not(None)))).all()
    reports = []
    for key in keys:
        try:
            reports.append(json.loads(await s3.download(key)))
        except Exception as exc:
            result.errors.append(f"{key}: {exc}")
    result.reports_read = len(reports)

    rows = rows_from_reports(reports)
    result.rows_built = len(rows)
    result.run_dates = sorted({r["run_date"].isoformat() for r in rows})

    if dry_run or not rows:
        return result

    await ensure_table(session)
    stmt = insert(RadarEntryHistory).values(rows).on_conflict_do_nothing(
        constraint="uq_radar_entry_history_tech_vendor_date"
    )
    result.rows_inserted = (await session.execute(stmt)).rowcount
    print(f"  [history] backfill inserted {result.rows_inserted} of {result.rows_built} rows")
    return result
