"""
Manually ingest S3 radar/competitor/regulatory JSON reports into the vector index.

In normal operation this runs automatically at the end of each pipeline.
Use this script to backfill historical reports or recover after an indexer failure.

Usage:
    uv run python scripts/ingest_reports.py              # ingest all reports
    uv run python scripts/ingest_reports.py --latest     # only latest per type
    uv run python scripts/ingest_reports.py --dry-run    # preview only, no POST

Cost: ~$0.001 per report (text-embedding-3-small)
"""

import argparse
import json
import sys
from pathlib import Path

import boto3
import httpx
from _aws import require_env

sys.path.insert(0, str(Path(__file__).parent.parent))
from aiplatform.agents.report_indexer import _CONVERTERS, _fmt_date
from aiplatform.settings import settings

API_URL = require_env("API_BASE")
INGEST_ENDPOINT = f"{API_URL}/api/v1/kp/ingest-skill"
BUCKET = settings.s3_bucket_name
REGION = settings.aws_region

REPORT_PREFIXES = {
    "radar":      "radar/reports/",
    "competitor": "competitor/reports/",
    "regulatory": "regulatory/reports/",
}


def list_report_keys(s3, report_type: str, latest_only: bool) -> list[str]:
    prefix = REPORT_PREFIXES[report_type]
    paginator = s3.get_paginator("list_objects_v2")
    keys = []
    for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".json") and "latest" not in key:
                keys.append(key)
    keys.sort()
    if latest_only and keys:
        return [keys[-1]]
    return keys


def download_json(s3, key: str) -> dict:
    resp = s3.get_object(Bucket=BUCKET, Key=key)
    return json.loads(resp["Body"].read())


def ingest_report(key: str, report_type: str, report: dict, dry_run: bool) -> str:
    label, converter = _CONVERTERS[report_type]
    content = converter(report)
    date = _fmt_date(report.get("generated_at", key))
    title = f"{label} Report — {date}"

    if dry_run:
        print(f"  [dry-run] would ingest: {title} ({len(content)} chars)")
        return "dry-run"

    payload = {
        "title": title,
        "content": content,
        "source_path": key,
        "category": report_type,
    }

    with httpx.Client(timeout=60.0) as client:
        resp = client.post(INGEST_ENDPOINT, json=payload)

    if resp.status_code == 200:
        data = resp.json()
        if data.get("skipped"):
            return "skipped"
        return f"ok ({data.get('chunks_created', 0)} chunks)"
    return f"error {resp.status_code}: {resp.text[:100]}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest S3 radar reports into vector index")
    parser.add_argument("--latest", action="store_true", help="Only ingest latest report per type")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no API calls")
    args = parser.parse_args()

    s3 = boto3.client("s3", region_name=REGION)
    total = ingested = skipped = errors = 0

    for report_type in ("radar", "competitor", "regulatory"):
        keys = list_report_keys(s3, report_type, args.latest)
        print(f"\n=== {report_type.upper()} ({len(keys)} reports) ===")

        for key in keys:
            total += 1
            try:
                report = download_json(s3, key)
                result = ingest_report(key, report_type, report, args.dry_run)
            except Exception as exc:
                result = f"error: {exc}"

            short_key = key.split("/")[-1]
            print(f"  [{result}] {short_key}")

            if result.startswith("ok"):
                ingested += 1
            elif result == "skipped":
                skipped += 1
            elif result.startswith("error"):
                errors += 1

    print(f"\nDone: total={total}  ingested={ingested}  skipped={skipped}  errors={errors}")


if __name__ == "__main__":
    main()
