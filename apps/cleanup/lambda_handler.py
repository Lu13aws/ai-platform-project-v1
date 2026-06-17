"""
Cleanup Lambda handler.

Triggered monthly by EventBridge. Deletes:
  - raw_articles where expires_at < NOW()  (30-day retention)
  - radar_reports older than 24 months + their S3 objects
"""

import asyncio
import json
import traceback

from aiplatform.agents.cleanup import CleanupAgent
from aiplatform.storage.database import get_async_session


async def _run_cleanup() -> dict:
    async with get_async_session() as session:
        result = await CleanupAgent().run(session)
    return {
        "articles_deleted": result.articles_deleted,
        "reports_deleted": result.reports_deleted,
        "s3_objects_deleted": result.s3_objects_deleted,
        "errors": result.errors,
    }


def handler(event, context):
    try:
        result = asyncio.run(_run_cleanup())
        print(f"[cleanup] done: {result}")
        return {"statusCode": 200, "body": json.dumps({"status": "ok", "result": result})}
    except Exception as exc:
        error_detail = traceback.format_exc()
        print(f"[cleanup] FAILED: {exc}\n{error_detail}")
        return {"statusCode": 500, "body": json.dumps({"status": "error", "error": str(exc)})}
