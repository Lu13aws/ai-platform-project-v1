"""
Competitor Reporter Agent — generates JSON + HTML report from this run's signals.

Loads all CompetitorSignals not yet linked to a report (report_id IS NULL),
groups by company, generates a dark-themed HTML report and JSON payload,
uploads both to S3, records the report in competitor_reports, and links
all signals via report_id FK.

S3 key pattern:
  competitor/reports/YYYY/MM/competitor_YYYYMMDD_HHMMSS.json
  competitor/reports/YYYY/MM/competitor_YYYYMMDD_HHMMSS.html
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from aiplatform.storage.competitor_models import (
    CompetitorReport,
    CompetitorSignal,
    CompetitorSource,
)
from aiplatform.storage.s3 import S3Client

_REPORT_PREFIX = "competitor/reports"
_LATEST_HTML_KEY = "competitor/reports/latest.html"
_LATEST_JSON_KEY = "competitor/reports/latest.json"
_SCHEMA_VERSION = 1

_IMPACT_COLORS = {"High": "#ef4444", "Medium": "#f59e0b", "Low": "#22c55e"}
_IMPACT_TEXT_COLORS = {"High": "#fecaca", "Medium": "#fef3c7", "Low": "#bbf7d0"}
_SENTIMENT_COLORS = {"positive": "#22c55e", "neutral": "#64748b", "negative": "#ef4444"}
_SIGNAL_TYPE_LABELS = {
    "product_announcement": "Product",
    "pricing_change": "Pricing",
    "financial_update": "Financial",
    "sentiment_event": "Community",
}
_COMPANY_COLORS = {
    "OpenAI": "#10a37f",
    "Anthropic": "#d97706",
    "Microsoft": "#0078d4",
    "AWS": "#ff9900",
    "Google": "#4285f4",
    "Mistral AI": "#7c3aed",
}


@dataclass
class CompetitorReportResult:
    company_count: int = 0
    signal_count: int = 0
    json_s3_uri: str = ""
    html_s3_uri: str = ""
    error: str = ""

    def __str__(self) -> str:
        if self.error:
            return f"error={self.error}"
        return (
            f"companies={self.company_count} "
            f"signals={self.signal_count} "
            f"json={self.json_s3_uri} "
            f"html={self.html_s3_uri}"
        )


class CompetitorReporterAgent:
    def __init__(self, s3: S3Client | None = None) -> None:
        self._s3 = s3 or S3Client()

    async def run(self, session: AsyncSession) -> CompetitorReportResult:
        result = CompetitorReportResult()
        now = datetime.now(UTC)

        # Load unlinked signals (this run)
        unlinked = (
            await session.scalars(
                select(CompetitorSignal)
                .where(CompetitorSignal.report_id.is_(None))
                .order_by(CompetitorSignal.signal_date.desc())
            )
        ).all()
        result.signal_count = len(unlinked)

        # Load all active sources for the monitored companies section
        sources = (
            await session.scalars(
                select(CompetitorSource)
                .where(CompetitorSource.active.is_(True))
                .order_by(CompetitorSource.company_name)
            )
        ).all()
        companies = sorted({s.company_name for s in sources})
        result.company_count = len(companies)

        # Group signals by company
        signals_by_company: dict[str, list] = {c: [] for c in companies}
        for sig in unlinked:
            if sig.company_name not in signals_by_company:
                signals_by_company[sig.company_name] = []
            signals_by_company[sig.company_name].append(sig)

        # Build JSON payload
        report = {
            "schema_version": _SCHEMA_VERSION,
            "generated_at": now.isoformat(),
            "summary": {
                "company_count": result.company_count,
                "signal_count": result.signal_count,
            },
            "companies": [
                {
                    "name": company,
                    "signals": [
                        {
                            "signal_type": s.signal_type,
                            "title": s.title,
                            "summary": s.summary,
                            "sentiment": s.sentiment,
                            "impact_level": s.impact_level,
                            "url": s.url,
                            "signal_date": s.signal_date.isoformat(),
                        }
                        for s in sorted(
                            signals_by_company.get(company, []),
                            key=lambda x: (
                                {"High": 0, "Medium": 1, "Low": 2}.get(x.impact_level, 3),
                            ),
                        )
                    ],
                }
                for company in companies
            ],
        }

        # S3 keys
        ts = now.strftime("%Y%m%d_%H%M%S")
        date_path = now.strftime("%Y/%m")
        json_key = f"{_REPORT_PREFIX}/{date_path}/competitor_{ts}.json"
        html_key = f"{_REPORT_PREFIX}/{date_path}/competitor_{ts}.html"

        json_bytes = json.dumps(report, indent=2, ensure_ascii=False).encode("utf-8")
        result.json_s3_uri = await self._s3.upload(json_key, json_bytes, "application/json")
        print(f"  [s3] {result.json_s3_uri}")

        html_bytes = _render_html(report).encode("utf-8")
        result.html_s3_uri = await self._s3.upload(html_key, html_bytes, "text/html; charset=utf-8")
        print(f"  [s3] {result.html_s3_uri}")

        # Overwrite stable "latest" keys — used by portfolio website (CloudFront URL never changes)
        await self._s3.upload(_LATEST_HTML_KEY, html_bytes, "text/html; charset=utf-8")
        await self._s3.upload(_LATEST_JSON_KEY, json_bytes, "application/json")
        print(f"  [s3] latest keys updated → {_LATEST_HTML_KEY}")

        # Record in DB
        db_report = CompetitorReport(
            generated_at=now,
            s3_key_json=json_key,
            s3_key_html=html_key,
            company_count=result.company_count,
            signal_count=result.signal_count,
            report_schema_version=_SCHEMA_VERSION,
        )
        session.add(db_report)
        await session.flush()

        # Link signals to report
        if unlinked:
            await session.execute(
                update(CompetitorSignal)
                .where(CompetitorSignal.id.in_([s.id for s in unlinked]))
                .values(report_id=db_report.id)
            )

        return result


# ── HTML renderer ──────────────────────────────────────────────────────────────

def _render_html(report: dict) -> str:
    generated_at = report["generated_at"][:19].replace("T", " ") + " UTC"
    summary = report["summary"]
    companies = report["companies"]

    # Collect unique companies for filter buttons
    all_companies = [c["name"] for c in companies if c["signals"]]

    companies_html = ""
    for company_data in companies:
        company = company_data["name"]
        signals = company_data["signals"]
        if not signals:
            continue
        color = _COMPANY_COLORS.get(company, "#64748b")
        signal_cards = ""
        for s in signals:
            ic = _IMPACT_COLORS.get(s["impact_level"], "#64748b")
            itc = _IMPACT_TEXT_COLORS.get(s["impact_level"], "#e2e8f0")
            sc = _SENTIMENT_COLORS.get(s["sentiment"], "#64748b")
            type_label = _SIGNAL_TYPE_LABELS.get(s["signal_type"], s["signal_type"])
            url_part = f'<a href="{_esc(s["url"])}" style="color:#38bdf8;font-size:0.75rem;text-decoration:none;">source</a>' if s.get("url") else ""
            signal_cards += f"""
      <div class="signal-card"
           data-company="{_esc(company)}"
           data-impact="{_esc(s['impact_level'])}"
           data-type="{_esc(s['signal_type'])}"
           data-sentiment="{_esc(s['sentiment'])}"
           style="background:#0f172a;border:1px solid #334155;border-radius:6px;padding:12px 16px;margin-bottom:8px;">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;flex-wrap:wrap;">
          <span style="background:{ic}22;color:{itc};border:1px solid {ic}44;border-radius:4px;padding:1px 8px;font-size:0.72rem;font-weight:700;">{_esc(s['impact_level'])}</span>
          <span style="background:#1e293b;border:1px solid #334155;color:#94a3b8;border-radius:4px;padding:1px 8px;font-size:0.72rem;">{_esc(type_label)}</span>
          <span style="color:{sc};font-size:0.72rem;">&#9679; {_esc(s['sentiment'])}</span>
          {url_part}
        </div>
        <div style="font-weight:600;color:#f1f5f9;font-size:0.88rem;margin-bottom:4px;">{_esc(s['title'])}</div>
        <div style="color:#94a3b8;font-size:0.82rem;line-height:1.5;word-break:break-word;overflow-wrap:break-word;">{_esc(s['summary'])}</div>
      </div>"""

        companies_html += f"""
    <div class="company-section" data-company="{_esc(company)}"
         style="background:#1e293b;border:1px solid #334155;border-left:4px solid {color};border-radius:8px;padding:20px 24px;margin-bottom:20px;">
      <h3 style="margin:0 0 12px;font-size:1.05rem;color:{color};">{_esc(company)}</h3>
      {signal_cards}
      <p class="no-results-msg" style="display:none;color:#475569;font-size:0.82rem;margin:0;">No signals match the current filters.</p>
    </div>"""

    if not companies_html:
        companies_html = '<p style="color:#475569;font-size:0.85rem;">No signals detected this week.</p>'

    # Build company filter buttons
    company_btns = '<button class="filter-btn active" data-group="company" data-value="all">All</button>'
    for c in all_companies:
        color = _COMPANY_COLORS.get(c, "#64748b")
        company_btns += f'<button class="filter-btn" data-group="company" data-value="{_esc(c)}" style="--accent:{color}">{_esc(c)}</button>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Competitor Radar</title>
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
    .filters {{ background: #1e293b; padding: 16px 40px; border-bottom: 1px solid #334155;
               display: flex; flex-direction: column; gap: 10px; }}
    .filter-row {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}
    .filter-label {{ font-size: 0.7rem; color: #475569; text-transform: uppercase;
                    letter-spacing: 0.05em; min-width: 70px; }}
    .filter-btn {{ background: transparent; border: 1px solid #334155; color: #64748b;
                  border-radius: 4px; padding: 3px 12px; font-size: 0.75rem; cursor: pointer;
                  transition: all 0.15s; }}
    .filter-btn:hover {{ border-color: #475569; color: #94a3b8; }}
    .filter-btn.active {{ background: var(--accent, #38bdf8); border-color: var(--accent, #38bdf8);
                         color: #0f172a; font-weight: 600; }}
    .filter-btn[data-value="High"].active {{ background:#ef4444;border-color:#ef4444;color:#fff; }}
    .filter-btn[data-value="Medium"].active {{ background:#f59e0b;border-color:#f59e0b;color:#0f172a; }}
    .filter-btn[data-value="Low"].active {{ background:#22c55e;border-color:#22c55e;color:#0f172a; }}
    #filter-count {{ font-size: 0.78rem; color: #475569; padding: 6px 0 0; }}
    main {{ padding: 32px 40px; max-width: 1100px; }}
    h2 {{ font-size: 1.1rem; font-weight: 600; color: #f1f5f9;
          margin: 0 0 20px; border-left: 5px solid #334155; padding-left: 12px; }}
    footer {{ text-align: center; padding: 24px; color: #334155; font-size: 0.8rem; }}
    @media (max-width: 640px) {{
      header, .filters {{ padding-left: 16px; padding-right: 16px; }}
      .stats {{ padding: 16px; gap: 16px; }}
      main {{ padding: 20px 16px; }}
      .stat .value {{ font-size: 1.4rem; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Competitor Radar</h1>
    <p>Generated {generated_at} &nbsp;·&nbsp;
       {summary['company_count']} companies monitored &nbsp;·&nbsp;
       {summary['signal_count']} signal{'s' if summary['signal_count'] != 1 else ''} this week</p>
  </header>
  <div class="stats">
    <div class="stat"><div class="value">{summary['company_count']}</div><div class="label">Companies</div></div>
    <div class="stat"><div class="value" id="visible-count">{summary['signal_count']}</div><div class="label">Signals</div></div>
  </div>

  <div class="filters">
    <div class="filter-row">
      <span class="filter-label">Company</span>
      {company_btns}
    </div>
    <div class="filter-row">
      <span class="filter-label">Impact</span>
      <button class="filter-btn active" data-group="impact" data-value="all">All</button>
      <button class="filter-btn" data-group="impact" data-value="High">High</button>
      <button class="filter-btn" data-group="impact" data-value="Medium">Medium</button>
      <button class="filter-btn" data-group="impact" data-value="Low">Low</button>
    </div>
    <div class="filter-row">
      <span class="filter-label">Type</span>
      <button class="filter-btn active" data-group="type" data-value="all">All</button>
      <button class="filter-btn" data-group="type" data-value="product_announcement">Product</button>
      <button class="filter-btn" data-group="type" data-value="pricing_change">Pricing</button>
      <button class="filter-btn" data-group="type" data-value="financial_update">Financial</button>
      <button class="filter-btn" data-group="type" data-value="sentiment_event">Sentiment</button>
    </div>
    <div class="filter-row">
      <span class="filter-label">Sentiment</span>
      <button class="filter-btn active" data-group="sentiment" data-value="all">All</button>
      <button class="filter-btn" data-group="sentiment" data-value="positive" style="--accent:#22c55e">Positive</button>
      <button class="filter-btn" data-group="sentiment" data-value="neutral" style="--accent:#94a3b8">Neutral</button>
      <button class="filter-btn" data-group="sentiment" data-value="negative" style="--accent:#ef4444">Negative</button>
    </div>
  </div>

  <main>
    <h2>Signals This Week</h2>
    {companies_html}
  </main>
  <footer>AI Platform &middot; Competitor Radar &middot; bridging-data.com</footer>

  <script>
    const state = {{ company: 'all', impact: 'all', type: 'all', sentiment: 'all' }};

    function applyFilters() {{
      let visible = 0;
      document.querySelectorAll('.company-section').forEach(section => {{
        const company = section.dataset.company;
        const companyMatch = state.company === 'all' || state.company === company;
        let sectionVisible = 0;

        section.querySelectorAll('.signal-card').forEach(card => {{
          const match = companyMatch
            && (state.impact   === 'all' || card.dataset.impact    === state.impact)
            && (state.type     === 'all' || card.dataset.type      === state.type)
            && (state.sentiment=== 'all' || card.dataset.sentiment === state.sentiment);
          card.style.display = match ? '' : 'none';
          if (match) sectionVisible++;
        }});

        section.style.display = sectionVisible > 0 ? '' : 'none';
        section.querySelector('.no-results-msg').style.display =
          (companyMatch && sectionVisible === 0) ? '' : 'none';
        visible += sectionVisible;
      }});
      document.getElementById('visible-count').textContent = visible;
    }}

    document.querySelectorAll('.filter-btn').forEach(btn => {{
      btn.addEventListener('click', () => {{
        const group = btn.dataset.group;
        document.querySelectorAll(`.filter-btn[data-group="${{group}}"]`).forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        state[group] = btn.dataset.value;
        applyFilters();
      }});
    }});
  </script>
</body>
</html>"""


def _esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
