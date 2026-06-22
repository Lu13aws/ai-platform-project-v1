"""
LinkedIn Post review service — CRUD for the UI review flow.

Status lifecycle:
  draft     → published  (via publish action)
  draft     → rejected   (via reject action)
  draft     → draft      (content updated by edit or regenerate)
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aiplatform.agents.content_creator_agent import ContentCreatorAgent
from aiplatform.agents.linkedin_publisher_agent import LinkedInPublisherAgent
from aiplatform.storage.content_models import LinkedInPost


async def list_posts(session: AsyncSession, status: str | None = None, limit: int = 20) -> list[LinkedInPost]:
    query = select(LinkedInPost).order_by(LinkedInPost.created_at.desc()).limit(limit)
    if status:
        query = query.where(LinkedInPost.status == status)
    result = await session.execute(query)
    return list(result.scalars().all())


async def edit_post(session: AsyncSession, post_id: uuid.UUID, content: str) -> LinkedInPost | None:
    post = await session.get(LinkedInPost, post_id)
    if post is None or post.status != "draft":
        return None
    post.content = content
    return post


async def regenerate_post(session: AsyncSession, post_id: uuid.UUID) -> LinkedInPost | None:
    post = await session.get(LinkedInPost, post_id)
    if post is None or post.status != "draft":
        return None
    new_content = await ContentCreatorAgent().regenerate(session, post)
    post.content = new_content
    return post


async def publish_post(session: AsyncSession, post_id: uuid.UUID) -> tuple[LinkedInPost | None, str]:
    post = await session.get(LinkedInPost, post_id)
    if post is None:
        return None, "Post not found"
    if post.status != "draft":
        return post, f"Post is already {post.status}"

    success = await LinkedInPublisherAgent().run(session, post)
    if success:
        post.status = "published"
        return post, "ok"
    else:
        return post, "LinkedIn API call failed — check credentials in Secrets Manager"


async def reject_post(session: AsyncSession, post_id: uuid.UUID) -> bool:
    post = await session.get(LinkedInPost, post_id)
    if post is None:
        return False
    post.status = "rejected"
    return True
