"""
Content Creator Pipeline Lambda handler.

Runs the full Content Creator pipeline in sequence:
  1. ContentCreatorAgent   — reads radar/competitor signals, LLM generates LinkedIn post
  2. LinkedInPublisherAgent — posts to LinkedIn API, stores post URL, sends SNS summary

Each agent runs in its own DB session so failures in later phases
do not roll back earlier committed data.

Triggered by EventBridge weekly schedule (Thursday 09:00 UTC).
"""

import asyncio
import json
import traceback

from aiplatform.agents.content_creator_agent import ContentCreatorAgent
from aiplatform.agents.linkedin_publisher_agent import LinkedInPublisherAgent
from aiplatform.storage.database import get_async_session


async def _run_pipeline() -> dict:
    results: dict[str, str] = {}

    print("[pipeline] phase 1/2 - content creator")
    async with get_async_session() as session:
        post = await ContentCreatorAgent().run(session)
    results["content_creator"] = f"post generated: {post.company} ({post.domain}/{post.angle})"
    print(f"[pipeline] content creator done: {results['content_creator']}")

    print("[pipeline] phase 2/2 - linkedin publisher")
    async with get_async_session() as session:
        # Re-fetch post in new session so we can update it
        from sqlalchemy import select
        from aiplatform.storage.content_models import LinkedInPost
        post_row = await session.get(LinkedInPost, post.id)
        if post_row is None:
            raise RuntimeError(f"Post {post.id} not found in new session")
        publisher = LinkedInPublisherAgent()
        success = await publisher.run(session, post_row)
    results["linkedin_publisher"] = "published" if success else "failed (see logs)"
    print(f"[pipeline] linkedin publisher done: {results['linkedin_publisher']}")

    return results


def handler(event, context):
    try:
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
    asyncio.run(_run_pipeline())
