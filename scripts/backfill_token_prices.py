#!/usr/bin/env python3
"""
Backfill Token Price Radar — fetch 24 months of LLM price history from LiteLLM GitHub.

One-time script. Safe to rerun — already-processed commits are skipped via
token_price_commits_processed table. Prices are only stored when they change
(delta detection against previous commit).

Usage:
    uv run python scripts/backfill_token_prices.py

Optional env vars:
    GITHUB_TOKEN   — GitHub personal access token (recommended: 5000 req/h vs 60/h anon)
    DRY_RUN=1      — print what would be written, don't touch DB or S3

Estimated runtime:
    ~100-200 commits over 24 months × 0.5s sleep = 1-2 minutes with GITHUB_TOKEN.
    Without token: same count at 60 req/h = ~90 minutes. Set GITHUB_TOKEN.
"""

import asyncio
import json
import os
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Allow running from repo root without install
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from aiplatform.agents.token_price_reporter import (
    TRACKED_MODELS,
    build_report_payload,
    derive_provider,
    extract_prices,
    fetch_commits_since,
    fetch_price_data_at_commit,
    _API_SLEEP,
    _LATEST_JSON_KEY,
    _REPORT_PREFIX,
)
from aiplatform.storage.database import engine, get_async_session
from aiplatform.storage.s3 import S3Client
from aiplatform.storage.token_price_models import (
    TokenPriceCommitProcessed,
    TokenPriceReport,
    TokenPriceSnapshot,
)

DRY_RUN = os.environ.get("DRY_RUN", "").strip() in ("1", "true", "yes")
BACKFILL_MONTHS = 24


async def _load_existing_shas(session) -> set[str]:
    return set(await session.scalars(select(TokenPriceCommitProcessed.commit_sha)))


async def _load_latest_prices(session) -> dict[str, dict]:
    """Load most recent known price per model for delta detection."""
    from sqlalchemy import text
    rows = await session.execute(
        text("""
            SELECT DISTINCT ON (model_id) model_id,
                   input_cost_per_token, output_cost_per_token
            FROM token_price_snapshots
            ORDER BY model_id, effective_date DESC
        """)
    )
    return {
        row.model_id: {
            "input_cost_per_token": row.input_cost_per_token,
            "output_cost_per_token": row.output_cost_per_token,
        }
        for row in rows
    }


async def run_backfill() -> None:
    now = datetime.now(UTC)
    since_dt = now - timedelta(days=BACKFILL_MONTHS * 30)
    since_iso = since_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"{'[DRY RUN] ' if DRY_RUN else ''}Token Price Radar — backfill {BACKFILL_MONTHS} months")
    print(f"  Fetching commits since {since_iso}")
    print(f"  Tracking {len(TRACKED_MODELS)} models")
    print(f"  GITHUB_TOKEN: {'set' if os.environ.get('GITHUB_TOKEN') else 'NOT SET (60 req/h limit!)'}")
    print()

    async with get_async_session() as session:
        existing_shas = await _load_existing_shas(session)
        prev_prices = await _load_latest_prices(session)

    print(f"  Already processed: {len(existing_shas)} commits")
    print(f"  Existing price snapshots for {len(prev_prices)} models")
    print()

    print("  Fetching commit list from GitHub...")
    commits = fetch_commits_since(since_iso)
    new_commits = [c for c in commits if c["sha"] not in existing_shas]
    print(f"  {len(commits)} total commits, {len(new_commits)} to process")
    print()

    if not new_commits:
        print("  Nothing to process. Proceeding to report generation.")

    total_snapshots_written = 0
    commits_processed = 0

    for i, commit in enumerate(new_commits, 1):
        sha = commit["sha"]
        committed_at_str = commit["commit"]["committer"]["date"]
        committed_at = datetime.fromisoformat(committed_at_str.replace("Z", "+00:00"))

        print(f"  [{i}/{len(new_commits)}] {sha[:8]} ({committed_at.date()}) ", end="", flush=True)

        try:
            price_data = fetch_price_data_at_commit(sha)
            time.sleep(_API_SLEEP)
        except Exception as exc:
            print(f"SKIP — {exc}")
            continue

        prices = extract_prices(price_data)
        new_price_rows = []

        for model_id, price in prices.items():
            prev = prev_prices.get(model_id)
            if prev and (
                prev["input_cost_per_token"] == price["input_cost_per_token"]
                and prev["output_cost_per_token"] == price["output_cost_per_token"]
            ):
                continue

            new_price_rows.append({
                "id": uuid.uuid4(),
                "model_id": model_id,
                "provider": derive_provider(model_id),
                "input_cost_per_token": price["input_cost_per_token"],
                "output_cost_per_token": price["output_cost_per_token"],
                "context_window": price.get("context_window"),
                "effective_date": committed_at,
                "source_commit_sha": sha,
                "source": "litellm_github",
                "created_at": now,
            })
            prev_prices[model_id] = price

        print(f"→ {len(new_price_rows)} price changes")

        if not DRY_RUN and new_price_rows:
            async with get_async_session() as session:
                for row in new_price_rows:
                    stmt = pg_insert(TokenPriceSnapshot).values(**row).on_conflict_do_nothing(
                        constraint="uq_token_price_model_date"
                    )
                    await session.execute(stmt)
                session.add(TokenPriceCommitProcessed(commit_sha=sha, processed_at=now))
        elif not DRY_RUN:
            async with get_async_session() as session:
                session.add(TokenPriceCommitProcessed(commit_sha=sha, processed_at=now))

        total_snapshots_written += len(new_price_rows)
        commits_processed += 1

    print()
    print(f"  Processed {commits_processed} commits, {total_snapshots_written} price snapshots written")
    print()

    # Generate and upload final report
    print("  Generating JSON report from all historical snapshots...")

    if DRY_RUN:
        print("  [DRY RUN] skipping S3 upload and report DB record")
        print()
        print("Backfill complete (dry run — no changes written).")
        return

    async with get_async_session() as session:
        all_snapshots = await session.scalars(
            select(TokenPriceSnapshot).order_by(
                TokenPriceSnapshot.model_id, TokenPriceSnapshot.effective_date
            )
        )

        snapshots_by_model: dict[str, list[dict]] = {}
        total_in_db = 0
        for snap in all_snapshots:
            snapshots_by_model.setdefault(snap.model_id, []).append({
                "effective_date": snap.effective_date,
                "input_cost_per_token": snap.input_cost_per_token,
                "output_cost_per_token": snap.output_cost_per_token,
                "context_window": snap.context_window,
                "source_commit_sha": snap.source_commit_sha,
            })
            total_in_db += 1

    report = build_report_payload(snapshots_by_model, now)
    json_bytes = json.dumps(report, indent=2, ensure_ascii=False).encode("utf-8")

    s3 = S3Client()
    ts = now.strftime("%Y%m%d_%H%M%S")
    date_path = now.strftime("%Y/%m")
    json_key = f"{_REPORT_PREFIX}/{date_path}/prices_{ts}.json"

    uri = await s3.upload(json_key, json_bytes, "application/json")
    print(f"  [s3] uploaded: {uri}")
    await s3.upload(_LATEST_JSON_KEY, json_bytes, "application/json")
    print(f"  [s3] latest key updated: {_LATEST_JSON_KEY}")

    async with get_async_session() as session:
        session.add(TokenPriceReport(
            generated_at=now,
            s3_key_json=json_key,
            model_count=len(snapshots_by_model),
            snapshot_count=total_in_db,
            report_schema_version=1,
        ))

    print()
    print("Backfill complete.")
    print(f"  Models in report : {report['summary']['model_count']}")
    print(f"  Providers        : {report['summary']['provider_count']}")
    print(f"  Date range       : {report['summary']['date_range_start']} → {report['summary']['date_range_end']}")
    print(f"  Total snapshots  : {total_in_db}")
    print(f"  S3 latest key    : {_LATEST_JSON_KEY}")
    print()
    print("Next steps:")
    print("  1. Verify: aws s3 cp s3://<bucket>/token-prices/reports/latest.json - | python -m json.tool | head -80")
    print("  2. Deploy Lambda: uv run python scripts/deploy_token_price_pipeline.py")


def main() -> None:
    try:
        asyncio.run(run_backfill())
    finally:
        asyncio.run(engine.dispose())


if __name__ == "__main__":
    main()
