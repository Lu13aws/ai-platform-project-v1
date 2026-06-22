"""
Content Creator Pipeline Lambda handler.

Runs ContentCreatorAgent weekly and saves the result as a draft.
Publishing is handled manually via the LinkedIn Review UI on platform.bridging-data.com.

Triggered by EventBridge weekly schedule (Thursday 09:00 UTC).
"""

import asyncio
import json
import traceback

from aiplatform.agents.content_creator_agent import ContentCreatorAgent
from aiplatform.storage.database import get_async_session


async def _run_pipeline() -> dict:
    print("[pipeline] content creator — generating LinkedIn draft")
    async with get_async_session() as session:
        post = await ContentCreatorAgent().run(session)

    return {
        "post_id": str(post.id),
        "company": post.company,
        "domain": post.domain,
        "angle": post.angle,
        "status": post.status,
        "chars": len(post.content),
    }


def handler(event, context):
    try:
        result = asyncio.run(_run_pipeline())
        print(f"[pipeline] draft saved: {result}")
        return {
            "statusCode": 200,
            "body": json.dumps({"status": "ok", "result": result}),
        }
    except Exception as exc:
        error_detail = traceback.format_exc()
        print(f"[pipeline] FAILED: {exc}\n{error_detail}")
        return {
            "statusCode": 500,
            "body": json.dumps({"status": "error", "error": str(exc)}),
        }


if __name__ == "__main__":
    asyncio.run(_run_pipeline())
