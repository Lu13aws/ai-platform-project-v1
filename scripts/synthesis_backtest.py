#!/usr/bin/env python3
"""
Phase 7 go/no-go check: would a two-domain SynthesisAgent have had anything to work with?

Replays every Technology Radar and Competitor Radar report JSON on S3 (read-only, no database,
no LLM) and counts, per month and company, the events both radars produced:

  radar events      : a tracked company's entry moved category, or appeared for the first time,
                      and still held in the next run (one-run flips are left out as noise).
                      Events in the newest run cannot be confirmed yet and are counted separately.
  competitor signals: unique signals (company, url, title); "pricing page updated" signals are
                      left out because they carry no price.
  topical match     : a competitor signal that names the moved technology (shared distinctive
                      word) - the closest thing to a real connection a synthesis could cite.

Usage:
    uv run python scripts/synthesis_backtest.py [--json out.json]
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import boto3

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiplatform.agents.radar_history import rows_from_reports  # noqa: E402
from aiplatform.agents.synthesis_entities import COMPANIES, companies_for_vendor  # noqa: E402
from aiplatform.settings import settings  # noqa: E402

_STOPWORDS = {
    "amazon", "aws", "anthropic", "google", "microsoft", "azure", "openai", "mistral", "with", "from",
    "support", "service", "services", "model", "models", "new", "for", "the", "and", "now", "available",
    "general", "availability", "preview", "cloud", "data", "agent", "agents", "platform", "api",
}


def _load_reports(s3, bucket: str, prefix: str, name_prefix: str) -> list[dict]:
    reports = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.rsplit("/", 1)[-1].startswith(name_prefix) and key.endswith(".json"):
                reports.append(json.loads(s3.get_object(Bucket=bucket, Key=key)["Body"].read()))
    return reports


def radar_events(radar_reports: list[dict]) -> tuple[list[dict], int]:
    """Confirmed category moves and new entries of tracked companies; plus the unconfirmed count."""
    rows = rows_from_reports(radar_reports)
    run_dates = sorted({r["run_date"] for r in rows})
    by_key: dict[tuple[str, str], dict] = defaultdict(dict)
    for r in rows:
        by_key[(r["technology_name"], r["vendor"])][r["run_date"]] = r["category"]

    events, unconfirmed = [], 0
    for i, run_date in enumerate(run_dates[1:], start=1):
        next_run = run_dates[i + 1] if i + 1 < len(run_dates) else None
        for r in (r for r in rows if r["run_date"] == run_date):
            companies = companies_for_vendor(r["vendor"])
            moved = r["previous_category"] not in (None, r["category"])
            new = r["previous_category"] is None
            if not companies or not (moved or new):
                continue
            if next_run is None:
                unconfirmed += 1
                continue
            if by_key[(r["technology_name"], r["vendor"])].get(next_run) != r["category"]:
                continue  # flipped back or vanished: noise
            for company in companies:
                events.append({
                    "company": company,
                    "month": run_date.strftime("%Y-%m"),
                    "kind": "move" if moved else "new",
                    "technology": r["technology_name"],
                    "change": f"{r['previous_category']} -> {r['category']}" if moved else f"new in {r['category']}",
                })
    return events, unconfirmed


def competitor_signals(competitor_reports: list[dict]) -> tuple[list[dict], Counter]:
    seen, signals, excluded = set(), [], Counter()
    for report in sorted(competitor_reports, key=lambda r: r["generated_at"]):
        for company in report.get("companies", []):
            for s in company["signals"]:
                key = (company["name"], s.get("url"), s["title"])
                if key in seen:
                    excluded["duplicate"] += 1
                    continue
                seen.add(key)
                if s["signal_type"] == "pricing_change" and s["title"].endswith("pricing page updated"):
                    excluded["pricing_page_updated"] += 1
                    continue
                signals.append({
                    "company": company["name"],
                    "month": datetime.fromisoformat(s["signal_date"]).strftime("%Y-%m"),
                    "type": s["signal_type"],
                    "impact": s.get("impact_level"),
                    "text": f"{s['title']} {s.get('summary', '')}".lower(),
                })
    return signals, excluded


def _distinctive_words(technology: str) -> set[str]:
    words = set(re.findall(r"[a-z0-9][a-z0-9.\-]{2,}", technology.lower()))
    return {w for w in words if w not in _STOPWORDS and len(w) >= 4}


def topical_matches(events: list[dict], signals: list[dict]) -> list[dict]:
    matches = []
    for e in events:
        words = _distinctive_words(e["technology"])
        if not words:
            continue
        for s in signals:
            if s["company"] == e["company"] and s["month"] == e["month"] and words & set(re.findall(r"[a-z0-9.\-]+", s["text"])):
                matches.append({**e, "signal_type": s["type"], "signal_text": s["text"][:140]})
                break
    return matches


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--json", type=Path, help="also write the full result to this file")
    args = parser.parse_args()

    s3 = boto3.client("s3", region_name=settings.aws_region)
    bucket = settings.s3_bucket_name
    radar = _load_reports(s3, bucket, "radar/reports/", "radar_")
    competitor = _load_reports(s3, bucket, "competitor/reports/", "competitor_")
    events, unconfirmed = radar_events(radar)
    signals, excluded = competitor_signals(competitor)
    matches = topical_matches(events, signals)

    print(f"radar reports {len(radar)}, competitor reports {len(competitor)}")
    print(f"radar events (confirmed) {len(events)}, unconfirmed (newest run) {unconfirmed}")
    print(f"competitor signals {len(signals)}, excluded {dict(excluded)}\n")

    months = sorted({e["month"] for e in events} | {s["month"] for s in signals})
    ev = Counter((e["month"], e["company"]) for e in events)
    sg = Counter((s["month"], s["company"]) for s in signals)
    tm = Counter((m["month"], m["company"]) for m in matches)
    print(f"{'month':8} " + " ".join(f"{c:>14}" for c in COMPANIES) + "   both  topical")
    for month in months:
        cells = [f"{ev[(month, c)]:>3}r/{sg[(month, c)]:>3}c{'*' if ev[(month, c)] and sg[(month, c)] else ' '}"
                 for c in COMPANIES]
        both = sum(1 for c in COMPANIES if ev[(month, c)] and sg[(month, c)])
        topical = sum(1 for c in COMPANIES if tm[(month, c)])
        print(f"{month:8} " + " ".join(f"{x:>14}" for x in cells) + f"   {both:>4}  {topical:>7}")
    print("\nr = radar events, c = competitor signals, * = both radars active for that company")

    print(f"\ntopical matches ({len(matches)}):")
    for m in matches:
        print(f"  {m['month']} {m['company']:10} {m['technology'][:45]:45} {m['change']:16} | {m['signal_type']}: {m['signal_text'][:70]}")

    if args.json:
        args.json.write_text(json.dumps(
            {"events": events, "unconfirmed": unconfirmed, "excluded": excluded, "matches": matches},
            indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
