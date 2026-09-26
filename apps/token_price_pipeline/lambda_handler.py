"""
Token Price Radar Pipeline Lambda handler.

Runs the Token Price Reporter Agent which:
  1. Fetches new commits to LiteLLM model_prices_and_context_window.json from GitHub
  2. Extracts price deltas for TRACKED_MODELS and stores in token_price_snapshots
  3. Generates a full historical JSON report and uploads to S3
  4. Records the run in token_price_reports

Triggered by EventBridge weekly schedule (Monday 07:00 UTC).

Env vars required:
    DATABASE_URL     — PostgreSQL connection string
    S3_BUCKET_NAME   — S3 bucket for report uploads
    GITHUB_TOKEN     — GitHub token (recommended; falls back to 60 req/h anonymous)

One-off actions (invoke manually with JSON payload):
    {"action": "migrate"}   — create token price tables (run once after first deploy)
    {"action": "run"}       — normal pipeline run (default, also used by EventBridge)
"""

import asyncio
import json
import traceback

from aiplatform.agents.token_price_reporter import TokenPriceReporterAgent
from aiplatform.storage.database import engine, get_async_session


async def _run_migrate() -> dict:
    """Create token price tables directly via SQLAlchemy (no alembic needed in Lambda)."""
    from aiplatform.storage.token_price_models import (
        TokenPriceCommitProcessed,
        TokenPriceReport,
        TokenPriceSnapshot,
    )
    from sqlalchemy import text

    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            for table in [
                TokenPriceSnapshot.__table__,
                TokenPriceCommitProcessed.__table__,
                TokenPriceReport.__table__,
            ]:
                await conn.run_sync(lambda sync_conn, t=table: t.create(sync_conn, checkfirst=True))
                print(f"  [migrate] {table.name} — ok")
        return {"migrated": True}
    finally:
        await engine.dispose()


async def _run_pipeline() -> dict:
    try:
        print("[pipeline] token price reporter")
        async with get_async_session() as session:
            result = await TokenPriceReporterAgent().run(session)
        print(f"[pipeline] done: {result}")
        return {"reporter": str(result)}
    finally:
        await engine.dispose()


def handler(event, context):
    action = (event or {}).get("action", "run")
    try:
        if action == "migrate":
            print("[pipeline] action=migrate — creating token price tables")
            results = asyncio.run(_run_migrate())
        else:
            results = asyncio.run(_run_pipeline())
        return {
            "statusCode": 200,
            "body": json.dumps({"status": "ok", "results": results}),
        }
    except Exception as exc:
        error_detail = traceback.format_exc()
        print(f"[pipeline] FAILED: {exc}\n{error_detail}")
        return {
            "statusCode": 500,
            "body": json.dumps({"status": "error", "error": str(exc)}),
        }


if __name__ == "__main__":
    # Local trigger: uv run python -m apps.token_price_pipeline.lambda_handler
    asyncio.run(_run_pipeline())
