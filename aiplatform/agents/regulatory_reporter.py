"""
Regulatory Reporter Agent — generates a JSON + HTML report from the current
pipeline run, uploads to S3, records in regulatory_reports, and links all
analyzed changes to the report.

S3 key pattern:
  regulatory/reports/YYYY/MM/regulatory_YYYYMMDD_HHMMSS.json
  regulatory/reports/YYYY/MM/regulatory_YYYYMMDD_HHMMSS.html

Retention: 24 months (managed via S3 lifecycle rule).
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from aiplatform.storage.regulatory_models import (
    RegulatoryChange,
    RegulatoryDocument,
    RegulatoryReport,
    RegulatorySource,
)
from aiplatform.storage.s3 import S3Client

_REPORT_PREFIX = "regulatory/reports"
_SCHEMA_VERSION = 1

_IMPACT_COLORS = {"High": "#ef4444", "Medium": "#f59e0b", "Low": "#22c55e"}
_IMPACT_TEXT_COLORS = {"High": "#fecaca", "Medium": "#fef3c7", "Low": "#bbf7d0"}
_DOMAIN_COLORS = {
    "Privacy": "#a855f7",
    "AI": "#3b82f6",
    "Cybersecurity": "#ef4444",
    "Compliance": "#f59e0b",
}


@dataclass
class RegulatoryReportResult:
    source_count: int = 0
    change_count: int = 0
    json_s3_uri: str = ""
    html_s3_uri: str = ""
    error: str = ""

    def __str__(self) -> str:
        if self.error:
            return f"error={self.error}"
        return (
            f"sources={self.source_count} "
            f"changes={self.change_count} "
            f"json={self.json_s3_uri} "
            f"html={self.html_s3_uri}"
        )


class RegulatoryReporterAgent:
    def __init__(self, s3: S3Client | None = None) -> None:
        self._s3 = s3 or S3Client()

    async def run(self, session: AsyncSession) -> RegulatoryReportResult:
        result = RegulatoryReportResult()
        now = datetime.now(UTC)

        # Load all sources (active + manual/inactive)
        sources = (
            await session.scalars(
                select(RegulatorySource).order_by(RegulatorySource.name)
            )
        ).all()
        result.source_count = len(sources)

        # Load unlinked changes (no report_id yet) — these are from this run
        unlinked_changes = (
            await session.scalars(
                select(RegulatoryChange)
                .where(RegulatoryChange.report_id.is_(None))
                .order_by(RegulatoryChange.detected_at.desc())
            )
        ).all()
        result.change_count = len(unlinked_changes)

        # Build source status map: source_id → latest document
        latest_docs: dict = {}
        for source in sources:
            doc = await session.scalar(
                select(RegulatoryDocument)
                .where(
                    RegulatoryDocument.source_id == source.id,
                    RegulatoryDocument.is_latest.is_(True),
                )
            )
            latest_docs[str(source.id)] = doc

        # Build source → change map
        change_by_source: dict = {}
        for change in unlinked_changes:
            change_by_source[str(change.source_id)] = change

        # Build report payload
        report = {
            "schema_version": _SCHEMA_VERSION,
            "generated_at": now.isoformat(),
            "summary": {
                "source_count": result.source_count,
                "change_count": result.change_count,
            },
            "changes": [
                {
                    "source_name": _source_name(sources, c.source_id),
                    "impact_level": c.impact_level,
                    "category": c.category,
                    "diff_summary": c.diff_summary,
                    "detected_at": c.detected_at.isoformat(),
                    "is_new_source": c.previous_document_id is None,
                }
                for c in unlinked_changes
            ],
            "sources": [
                {
                    "name": s.name,
                    "domain": s.domain,
                    "url": s.url if s.active else None,
                    "last_checked_at": s.last_checked_at.isoformat() if s.last_checked_at else None,
                    "has_change_this_run": str(s.id) in change_by_source,
                    "is_manual": not s.active,
                }
                for s in sources
            ],
        }

        # S3 keys
        ts = now.strftime("%Y%m%d_%H%M%S")
        date_path = now.strftime("%Y/%m")
        json_key = f"{_REPORT_PREFIX}/{date_path}/regulatory_{ts}.json"
        html_key = f"{_REPORT_PREFIX}/{date_path}/regulatory_{ts}.html"

        # Upload JSON
        json_bytes = json.dumps(report, indent=2, ensure_ascii=False).encode("utf-8")
        result.json_s3_uri = await self._s3.upload(json_key, json_bytes, "application/json")
        print(f"  [s3] {result.json_s3_uri}")

        # Upload HTML
        html_bytes = _render_html(report).encode("utf-8")
        result.html_s3_uri = await self._s3.upload(html_key, html_bytes, "text/html; charset=utf-8")
        print(f"  [s3] {result.html_s3_uri}")

        # Record report in DB
        db_report = RegulatoryReport(
            generated_at=now,
            s3_key_json=json_key,
            s3_key_html=html_key,
            source_count=result.source_count,
            change_count=result.change_count,
            report_schema_version=_SCHEMA_VERSION,
        )
        session.add(db_report)
        await session.flush()  # get db_report.id

        # Link all unlinked changes to this report
        if unlinked_changes:
            change_ids = [c.id for c in unlinked_changes]
            await session.execute(
                update(RegulatoryChange)
                .where(RegulatoryChange.id.in_(change_ids))
                .values(report_id=db_report.id)
            )

        return result


# ── HTML renderer ──────────────────────────────────────────────────────────────

def _render_html(report: dict) -> str:
    generated_at = report["generated_at"][:19].replace("T", " ") + " UTC"
    summary = report["summary"]
    changes = report["changes"]
    sources = report["sources"]

    changes_section = _render_changes(changes)
    sources_section = _render_sources(sources)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Regulatory Radar</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           margin: 0; background: #0f172a; color: #e2e8f0; }}
    header {{ background: #1e293b; padding: 24px 40px; border-bottom: 1px solid #334155; }}
    header h1 {{ margin: 0 0 4px; font-size: 1.6rem; color: #f8fafc; }}
    header p {{ margin: 0; font-size: 0.85rem; color: #94a3b8; }}
    .stats {{ display: flex; gap: 32px; padding: 20px 40px; background: #1e293b;
              border-bottom: 1px solid #334155; }}
    .stat .value {{ font-size: 1.8rem; font-weight: 700; color: #38bdf8; }}
    .stat .label {{ font-size: 0.75rem; color: #64748b; text-transform: uppercase; }}
    main {{ padding: 32px 40px; max-width: 1100px; }}
    section {{ margin-bottom: 40px; }}
    h2 {{ font-size: 1.1rem; font-weight: 600; color: #f1f5f9;
          margin: 0 0 16px; display: flex; align-items: center; gap: 10px; }}
    .count-badge {{ background: #334155; color: #94a3b8; border-radius: 12px;
                    padding: 2px 10px; font-size: 0.8rem; }}
    /* Change cards */
    .change-card {{ background: #1e293b; border: 1px solid #334155; border-radius: 8px;
                    padding: 16px 20px; margin-bottom: 12px; }}
    .change-header {{ display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }}
    .impact-badge {{ border-radius: 4px; padding: 2px 10px; font-size: 0.75rem; font-weight: 700; }}
    .domain-badge {{ border-radius: 4px; padding: 2px 10px; font-size: 0.75rem;
                     background: #1e293b; border: 1px solid #334155; color: #94a3b8; }}
    .source-label {{ font-weight: 600; color: #f1f5f9; font-size: 0.9rem; }}
    .new-badge {{ font-size: 0.7rem; color: #a78bfa; background: #1e1b4b;
                  border: 1px solid #4c1d95; border-radius: 4px; padding: 1px 6px; }}
    .diff-summary {{ font-size: 0.85rem; color: #94a3b8; line-height: 1.6; margin: 0; }}
    /* Sources table */
    .sources-table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
    .sources-table th {{ text-align: left; padding: 8px 12px; color: #64748b;
                         border-bottom: 1px solid #334155; font-weight: 500; }}
    .sources-table td {{ padding: 8px 12px; border-bottom: 1px solid #1e293b; color: #cbd5e1; }}
    .dot-green {{ color: #22c55e; }}
    .dot-gray {{ color: #475569; }}
    footer {{ text-align: center; padding: 24px; color: #334155; font-size: 0.8rem; }}
  </style>
</head>
<body>
  <header>
    <h1>Regulatory Radar</h1>
    <p>Generated {generated_at} &nbsp;·&nbsp;
       {summary['source_count']} sources monitored &nbsp;·&nbsp;
       {summary['change_count']} change{'s' if summary['change_count'] != 1 else ''} this run</p>
  </header>
  <div class="stats">
    <div class="stat"><div class="value">{summary['source_count']}</div><div class="label">Sources</div></div>
    <div class="stat"><div class="value">{summary['change_count']}</div><div class="label">Changes</div></div>
  </div>
  <main>
    {changes_section}
    {sources_section}
  </main>
  <footer>AI Platform · Regulatory Radar · bridging-data.com</footer>
</body>
</html>"""


def _render_changes(changes: list[dict]) -> str:
    if not changes:
        return """<section>
  <h2 style="border-left: 5px solid #22c55e; padding-left: 12px;">No Changes This Run</h2>
  <p style="color: #475569; font-size: 0.85rem;">All monitored sources are unchanged.</p>
</section>"""

    cards = ""
    for c in changes:
        color = _IMPACT_COLORS.get(c["impact_level"], "#64748b")
        text_color = _IMPACT_TEXT_COLORS.get(c["impact_level"], "#e2e8f0")
        domain_color = _DOMAIN_COLORS.get(c["category"], "#64748b")
        new_label = '<span class="new-badge">INITIAL CAPTURE</span>' if c["is_new_source"] else ""
        cards += f"""
    <div class="change-card">
      <div class="change-header">
        <span class="impact-badge" style="background:{color}22; color:{text_color}; border: 1px solid {color}44;">
          {_esc(c['impact_level'])}
        </span>
        <span class="domain-badge" style="border-color:{domain_color}44; color:{domain_color};">
          {_esc(c['category'])}
        </span>
        <span class="source-label">{_esc(c['source_name'])}</span>
        {new_label}
      </div>
      <p class="diff-summary">{_esc(c['diff_summary'])}</p>
    </div>"""

    return f"""<section>
  <h2 style="border-left: 5px solid #ef4444; padding-left: 12px;">
    Changes Detected <span class="count-badge">{len(changes)}</span>
  </h2>
  {cards}
</section>"""


def _render_sources(sources: list[dict]) -> str:
    rows = ""
    for s in sources:
        dot = '<span class="dot-green">●</span>' if s["has_change_this_run"] else '<span class="dot-gray">●</span>'
        checked = s["last_checked_at"][:10] if s["last_checked_at"] else "—"
        domain_color = _DOMAIN_COLORS.get(s["domain"], "#64748b")
        manual_tag = ' <span style="font-size:0.7rem;color:#64748b;background:#1e293b;border:1px solid #334155;border-radius:4px;padding:1px 5px;">manual</span>' if s.get("is_manual") else ""
        name_cell = (
            f'<a href="{_esc(s["url"])}" style="color:#38bdf8; text-decoration:none;">{_esc(s["name"])}</a>'
            if s["url"]
            else f'<span style="color:#cbd5e1;">{_esc(s["name"])}</span>'
        )
        rows += f"""
    <tr>
      <td>{dot}</td>
      <td>{name_cell}{manual_tag}</td>
      <td><span style="color:{domain_color}; font-size:0.78rem;">{_esc(s['domain'])}</span></td>
      <td style="color:#64748b;">{checked}</td>
    </tr>"""

    return f"""<section>
  <h2 style="border-left: 5px solid #334155; padding-left: 12px;">
    Monitored Sources <span class="count-badge">{len(sources)}</span>
  </h2>
  <table class="sources-table">
    <thead><tr><th></th><th>Source</th><th>Domain</th><th>Last Checked</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</section>"""


def _source_name(sources: list, source_id: object) -> str:
    for s in sources:
        if s.id == source_id:
            return s.name
    return str(source_id)


def _esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
