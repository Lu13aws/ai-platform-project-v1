"""
ReportIndexerAgent — indexes a generated JSON report into the vector store.

Called directly from pipeline lambda handlers after the reporter phase.
Uses ingest_skill() without HTTP, so it works inside the same Lambda process.

Dedup is handled by ingest_skill via SHA-256 content hash.
If the report content hasn't changed since last run, ingest is skipped (free).
"""

import json
from datetime import datetime

import boto3

from aiplatform.settings import settings

# ── Text converters (single source of truth — imported by scripts/ingest_reports.py) ──

def _fmt_date(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%Y-%m-%d")
    except Exception:
        return iso[:10]


def radar_to_text(report: dict) -> str:
    date = _fmt_date(report.get("generated_at", ""))
    lines = [
        f"Technology Radar Report — {date}",
        f"Signals analysed: {report['summary'].get('signal_count', 0)} | "
        f"Technologies tracked: {report['summary'].get('entry_count', 0)}",
        "",
    ]
    for category, entries in report.get("entries", {}).items():
        if not entries:
            continue
        lines.append(f"## {category}")
        for e in entries:
            lines.append(
                f"- {e['technology_name']} ({e['vendor']}): {e.get('summary', '')} "
                f"[trend: {e.get('trend', 'unknown')}]"
            )
        lines.append("")
    return "\n".join(lines)


def competitor_to_text(report: dict) -> str:
    date = _fmt_date(report.get("generated_at", ""))
    lines = [
        f"Competitor Radar Report — {date}",
        f"Companies monitored: {report['summary'].get('company_count', 0)} | "
        f"Signals: {report['summary'].get('signal_count', 0)}",
        "",
    ]
    for company in report.get("companies", []):
        lines.append(f"## {company['name']}")
        for sig in company.get("signals", []):
            lines.append(
                f"- [{sig.get('impact_level','?')} / {sig.get('sentiment','?')}] "
                f"{sig['title']}: {sig.get('summary', '')}"
            )
        lines.append("")
    return "\n".join(lines)


def regulatory_to_text(report: dict) -> str:
    date = _fmt_date(report.get("generated_at", ""))
    lines = [
        f"Regulatory Changes Report — {date}",
        f"Sources monitored: {report['summary'].get('source_count', 0)} | "
        f"Changes detected: {report['summary'].get('change_count', 0)}",
        "",
    ]
    sources = {s["name"] for s in report.get("sources", [])}
    if sources:
        lines.append(f"Sources: {', '.join(sorted(sources))}")
        lines.append("")
    changes = report.get("changes", [])
    if changes:
        lines.append("## Detected Changes")
        for c in changes:
            lines.append(
                f"- [{c.get('impact_level','?')} / {c.get('category','?')}] "
                f"{c.get('diff_summary', '')}"
            )
    else:
        lines.append("No changes detected in this report.")
    return "\n".join(lines)


_CONVERTERS: dict[str, tuple[str, object]] = {
    "radar":      ("Technology Radar",   radar_to_text),
    "competitor": ("Competitor Radar",   competitor_to_text),
    "regulatory": ("Regulatory Changes", regulatory_to_text),
}


# ── Agent ──────────────────────────────────────────────────────────────────────

class ReportIndexerAgent:
    """Index a freshly generated report JSON from S3 into the vector store."""

    def __init__(self) -> None:
        self._s3 = boto3.client("s3", region_name=settings.aws_region)

    async def index_report(
        self,
        report_type: str,
        s3_uri: str,
    ) -> str:
        """
        Download the JSON from s3_uri, convert to text, and call ingest_skill.

        Uses its own DB session so any ingest error doesn't corrupt the pipeline session.
        Returns a short status string: "ok (N chunks)", "skipped", or "error: ..."
        """
        from apps.knowledge_platform.api.schemas import IngestSkillRequest
        from apps.knowledge_platform.services.platform_service import ingest_skill

        from aiplatform.storage.database import get_async_session

        if not s3_uri:
            return "skipped (no s3_uri)"

        label, converter = _CONVERTERS.get(report_type, (report_type, str))

        try:
            s3_key = _uri_to_key(s3_uri)
            report = self._download_json(s3_key)
            content = converter(report)
            date = _fmt_date(report.get("generated_at", s3_key))

            request = IngestSkillRequest(
                title=f"{label} Report — {date}",
                content=content,
                source_path=s3_key,
                category=report_type,
            )
            async with get_async_session() as session:
                response = await ingest_skill(session, request)

            if response.skipped:
                return "skipped"
            return f"ok ({response.chunks_created} chunks)"

        except Exception as exc:
            print(f"  [indexer] error indexing {s3_uri}: {exc}")
            return f"error: {exc}"

    def _download_json(self, s3_key: str) -> dict:
        resp = self._s3.get_object(Bucket=settings.s3_bucket_name, Key=s3_key)
        return json.loads(resp["Body"].read())


def _uri_to_key(s3_uri: str) -> str:
    """'s3://bucket/path/to/key' → 'path/to/key'"""
    without_scheme = s3_uri[len("s3://"):]
    return without_scheme.split("/", 1)[1]
