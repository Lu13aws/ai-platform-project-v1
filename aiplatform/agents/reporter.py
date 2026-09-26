"""
Report Agent — generates a Technology Radar report from radar_entries,
uploads JSON + HTML to S3, and records the run in radar_reports.

S3 key pattern:
  radar/reports/YYYY/MM/radar_YYYYMMDD_HHMMSS.json
  radar/reports/YYYY/MM/radar_YYYYMMDD_HHMMSS.html

Retention: 24 months (managed externally via S3 lifecycle rule).
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aiplatform.agents.report_utils import esc as _esc
from aiplatform.storage.radar_models import RadarEntry, RadarReport, RadarSignal, RadarSource
from aiplatform.storage.s3 import S3Client

if TYPE_CHECKING:
    from aiplatform.agents.change_detector import ChangeReport

_REPORT_PREFIX = "radar/reports"
_CATEGORIES = ["Adopt", "Trial", "Assess", "Hold"]
_SCHEMA_VERSION = 1

_CATEGORY_COLORS = {
    "Adopt": "#22c55e",
    "Trial": "#3b82f6",
    "Assess": "#f59e0b",
    "Hold": "#ef4444",
}
_TREND_ICONS = {"up": "↑", "stable": "→", "down": "↓"}


@dataclass
class ReportResult:
    entry_count: int = 0
    signal_count: int = 0
    source_count: int = 0
    json_s3_uri: str = ""
    html_s3_uri: str = ""
    error: str = ""

    def __str__(self) -> str:
        if self.error:
            return f"error={self.error}"
        return (
            f"entries={self.entry_count} "
            f"signals={self.signal_count} "
            f"sources={self.source_count} "
            f"json={self.json_s3_uri} "
            f"html={self.html_s3_uri}"
        )


class ReporterAgent:
    def __init__(self, s3: S3Client | None = None, change_report: "ChangeReport | None" = None) -> None:
        self._s3 = s3 or S3Client(prefix=_REPORT_PREFIX)
        self._change_report = change_report

    async def run(self, session: AsyncSession) -> ReportResult:
        result = ReportResult()
        now = datetime.now(UTC)

        entries = (
            await session.scalars(select(RadarEntry).order_by(RadarEntry.category, RadarEntry.technology_name))
        ).all()

        source_count = await session.scalar(select(func.count()).select_from(RadarSource))
        signal_count = await session.scalar(select(func.count()).select_from(RadarSignal))

        result.entry_count = len(entries)
        result.source_count = source_count or 0
        result.signal_count = signal_count or 0

        if not entries:
            result.error = "no radar entries — run analyzer first"
            return result

        # Build report dict
        by_category: dict[str, list[dict]] = {c: [] for c in _CATEGORIES}
        for entry in entries:
            cat = entry.category if entry.category in _CATEGORIES else "Assess"
            by_category[cat].append({
                "technology_name": entry.technology_name,
                "vendor": entry.vendor,
                "category": cat,
                "summary": entry.summary,
                "trend": entry.trend,
                "signal_count": entry.signal_count,
                "last_updated_at": entry.last_updated_at.isoformat(),
            })

        report = {
            "schema_version": _SCHEMA_VERSION,
            "generated_at": now.isoformat(),
            "summary": {
                "source_count": result.source_count,
                "signal_count": result.signal_count,
                "entry_count": result.entry_count,
            },
            "entries": by_category,
        }

        # S3 key with timestamp
        ts = now.strftime("%Y%m%d_%H%M%S")
        date_path = now.strftime("%Y/%m")
        json_key = f"{_REPORT_PREFIX}/{date_path}/radar_{ts}.json"
        html_key = f"{_REPORT_PREFIX}/{date_path}/radar_{ts}.html"

        # Upload JSON
        json_bytes = json.dumps(report, indent=2, ensure_ascii=False).encode("utf-8")
        result.json_s3_uri = await self._s3.upload(json_key, json_bytes, "application/json")
        print(f"  [s3] {result.json_s3_uri}")

        # Upload HTML
        html_bytes = _render_html(report, self._change_report).encode("utf-8")
        result.html_s3_uri = await self._s3.upload(html_key, html_bytes, "text/html; charset=utf-8")
        print(f"  [s3] {result.html_s3_uri}")

        # Record in DB
        session.add(RadarReport(
            generated_at=now,
            s3_key=json_key,
            source_count=result.source_count,
            signal_count=result.signal_count,
            entry_count=result.entry_count,
            report_schema_version=_SCHEMA_VERSION,
        ))

        return result


# ─────────────────────────────────────────────────────────────────────────────
# HTML renderer
# ─────────────────────────────────────────────────────────────────────────────

def _render_html(report: dict, change_report: "ChangeReport | None" = None) -> str:
    generated_at = report["generated_at"][:19].replace("T", " ") + " UTC"
    summary = report["summary"]
    entries_by_cat = report["entries"]

    category_sections = ""
    for cat in _CATEGORIES:
        entries = entries_by_cat.get(cat, [])
        color = _CATEGORY_COLORS[cat]
        cards = ""
        for e in entries:
            trend_icon = _TREND_ICONS.get(e["trend"], "→")
            cards += f"""
            <div class="card">
              <div class="card-header">
                <span class="tech-name">{_esc(e['technology_name'])}</span>
                <span class="trend" title="trend">{trend_icon}</span>
              </div>
              <div class="vendor">{_esc(e['vendor'])}</div>
              <p class="summary">{_esc(e['summary'])}</p>
              <div class="meta">signals: {e['signal_count']}</div>
            </div>"""

        count_badge = f'<span class="count-badge">{len(entries)}</span>'
        category_sections += f"""
        <section class="category">
          <h2 style="border-left: 5px solid {color}; padding-left: 12px;">
            {cat} {count_badge}
          </h2>
          <div class="cards">
            {cards if cards else '<p class="empty">No entries in this category.</p>'}
          </div>
        </section>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Technology Radar</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           margin: 0; background: #0f172a; color: #e2e8f0; }}
    header {{ background: #1e293b; padding: 24px 40px; border-bottom: 1px solid #334155; }}
    header h1 {{ margin: 0 0 4px; font-size: 1.6rem; color: #f8fafc; }}
    header p {{ margin: 0; font-size: 0.85rem; color: #94a3b8; }}
    .stats {{ display: flex; gap: 24px; padding: 20px 40px; background: #1e293b;
              border-bottom: 1px solid #334155; }}
    .stat {{ text-align: center; }}
    .stat .value {{ font-size: 1.8rem; font-weight: 700; color: #38bdf8; }}
    .stat .label {{ font-size: 0.75rem; color: #64748b; text-transform: uppercase; }}
    main {{ padding: 32px 40px; max-width: 1200px; }}
    .category {{ margin-bottom: 40px; }}
    .category h2 {{ font-size: 1.1rem; font-weight: 600; color: #f1f5f9;
                    margin: 0 0 16px; display: flex; align-items: center; gap: 10px; }}
    .count-badge {{ background: #334155; color: #94a3b8; border-radius: 12px;
                    padding: 2px 10px; font-size: 0.8rem; font-weight: 500; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }}
    .card {{ background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 16px; }}
    .card-header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 4px; }}
    .tech-name {{ font-weight: 600; color: #f1f5f9; font-size: 0.95rem; }}
    .trend {{ font-size: 1.1rem; color: #64748b; }}
    .vendor {{ font-size: 0.78rem; color: #64748b; margin-bottom: 10px; }}
    .summary {{ font-size: 0.85rem; color: #94a3b8; margin: 0 0 10px; line-height: 1.5; }}
    .meta {{ font-size: 0.75rem; color: #475569; }}
    .empty {{ color: #475569; font-style: italic; font-size: 0.85rem; }}
    .changes {{ margin-bottom: 40px; }}
    .change-table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
    .change-table th {{ text-align: left; padding: 8px 12px; color: #64748b;
                        border-bottom: 1px solid #334155; font-weight: 500; }}
    .change-table td {{ padding: 8px 12px; border-bottom: 1px solid #1e293b; color: #cbd5e1; }}
    .badge {{ border-radius: 4px; padding: 2px 8px; font-size: 0.75rem; font-weight: 600; white-space: nowrap; }}
    .badge.new {{ background: #6d28d9; color: #ede9fe; }}
    .badge.up {{ background: #166534; color: #bbf7d0; }}
    .badge.down {{ background: #991b1b; color: #fecaca; }}
    footer {{ text-align: center; padding: 24px; color: #334155; font-size: 0.8rem; }}
  </style>
</head>
<body>
  <header>
    <h1>Technology Radar</h1>
    <p>Generated {generated_at} &nbsp;·&nbsp;
       {summary['source_count']} sources &nbsp;·&nbsp;
       {summary['signal_count']} signals &nbsp;·&nbsp;
       {summary['entry_count']} technologies</p>
  </header>
  <div class="stats">
    <div class="stat"><div class="value">{summary['entry_count']}</div><div class="label">Technologies</div></div>
    <div class="stat"><div class="value">{summary['signal_count']}</div><div class="label">Signals</div></div>
    <div class="stat"><div class="value">{summary['source_count']}</div><div class="label">Sources</div></div>
  </div>
  <main>
    {_render_changes_section(change_report)}
    {category_sections}
  </main>
  <footer>AI Platform · Technology Radar · bridging-data.com</footer>
</body>
</html>"""


def _render_changes_section(change_report: "ChangeReport | None") -> str:
    if not change_report or not change_report.has_changes():
        return ""

    rows = ""
    for e in change_report.new_entries:
        rows += f'<tr><td class="badge new">NEW</td><td>{_esc(e.technology_name)}</td><td>{_esc(e.vendor)}</td><td>—</td><td>{_esc(e.current_category)}</td></tr>'
    for e in change_report.moved_up:
        rows += f'<tr><td class="badge up">↑ UP</td><td>{_esc(e.technology_name)}</td><td>{_esc(e.vendor)}</td><td>{_esc(e.previous_category or "")}</td><td>{_esc(e.current_category)}</td></tr>'
    for e in change_report.moved_down:
        rows += f'<tr><td class="badge down">↓ DOWN</td><td>{_esc(e.technology_name)}</td><td>{_esc(e.vendor)}</td><td>{_esc(e.previous_category or "")}</td><td>{_esc(e.current_category)}</td></tr>'

    return f"""
    <section class="changes">
      <h2 style="border-left: 5px solid #a855f7; padding-left: 12px;">
        What Changed <span class="count-badge">{change_report.total_changes()}</span>
      </h2>
      <table class="change-table">
        <thead><tr><th>Change</th><th>Technology</th><th>Vendor</th><th>From</th><th>To</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </section>"""
