import base64
import json
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession


async def _require_corp_admin(authorization: str = Header(default=None)) -> None:
    """Lightweight JWT group check — verifies corp-admins membership from Cognito IdToken.

    Does NOT verify the JWT signature (no Cognito public key fetch).
    The claim is trusted for this internal demo; a production system
    should verify against Cognito's JWKS endpoint.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization header required")
    try:
        token = authorization[7:]  # strip "Bearer "
        segment = token.split(".")[1]
        # Restore base64 padding
        segment += "=" * (-len(segment) % 4)
        payload = json.loads(base64.b64decode(segment))
        raw_groups = payload.get("cognito:groups", [])
        groups: list[str] = raw_groups if isinstance(raw_groups, list) else str(raw_groups).strip("[]").split()
        if "corp-admins" not in groups:
            raise HTTPException(status_code=403, detail="corp-admins group required")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

from aiplatform.storage.database import get_session
from apps.knowledge_platform.api.schemas import (
    AgentHeartbeatRequest,
    AgentHeartbeatResponse,
    AgentsResponse,
    EditPostRequest,
    IngestSkillRequest,
    IngestSkillResponse,
    LinkedInPostItem,
    LinkedInPostsResponse,
    PublishPostResponse,
    QueryRequest,
    QueryResponse,
    RecentActivityResponse,
    ReportsResponse,
    SkillsResponse,
    StatsResponse,
)
from apps.knowledge_platform.services.linkedin_service import (
    edit_post,
    list_posts,
    publish_post,
    regenerate_post,
    reject_post,
)
from apps.knowledge_platform.services.platform_service import (
    get_agent_statuses,
    get_all_reports,
    get_recent_activity,
    get_skills,
    get_stats,
    ingest_skill,
    record_heartbeat,
)
from apps.rag_demo.services.query_service import QueryService

router = APIRouter(prefix="/kp", tags=["knowledge-platform"])


@router.get("/stats", response_model=StatsResponse)
async def stats(session: AsyncSession = Depends(get_session)) -> StatsResponse:
    data = await get_stats(session)
    return StatsResponse(**data)


@router.get("/recent", response_model=RecentActivityResponse)
async def recent(session: AsyncSession = Depends(get_session)) -> RecentActivityResponse:
    items = await get_recent_activity(session)
    return RecentActivityResponse(items=items)


@router.get("/reports", response_model=ReportsResponse)
async def reports(session: AsyncSession = Depends(get_session)) -> ReportsResponse:
    items = await get_all_reports(session)
    return ReportsResponse(total=len(items), reports=items)


@router.get("/agents", response_model=AgentsResponse)
async def agents(session: AsyncSession = Depends(get_session)) -> AgentsResponse:
    statuses = await get_agent_statuses(session)
    return AgentsResponse(agents=statuses)


@router.get("/skills", response_model=SkillsResponse)
async def skills(session: AsyncSession = Depends(get_session)) -> SkillsResponse:
    items = await get_skills(session)
    return SkillsResponse(total=len(items), skills=items)


@router.post("/query", response_model=QueryResponse)
async def query(
    request: QueryRequest,
    session: AsyncSession = Depends(get_session),
) -> QueryResponse:
    service = QueryService(session, app_name=None)  # search across all indexed content
    return await service.query(request)


@router.post("/ingest-skill", response_model=IngestSkillResponse)
async def ingest_skill_endpoint(
    request: IngestSkillRequest,
    session: AsyncSession = Depends(get_session),
) -> IngestSkillResponse:
    return await ingest_skill(session, request)


@router.post("/agent-heartbeat", response_model=AgentHeartbeatResponse)
async def agent_heartbeat_endpoint(
    request: AgentHeartbeatRequest,
    session: AsyncSession = Depends(get_session),
) -> AgentHeartbeatResponse:
    return await record_heartbeat(session, request)


# ── LinkedIn Review ────────────────────────────────────────────────────────────

def _post_to_item(p) -> LinkedInPostItem:
    return LinkedInPostItem(
        id=str(p.id),
        domain=p.domain,
        angle=p.angle,
        company=p.company,
        content=p.content,
        status=p.status,
        linkedin_post_url=p.linkedin_post_url,
        posted_at=p.posted_at,
        created_at=p.created_at,
    )


@router.get("/linkedin", response_model=LinkedInPostsResponse,
            dependencies=[Depends(_require_corp_admin)])
async def linkedin_posts(
    status: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> LinkedInPostsResponse:
    posts = await list_posts(session, status=status)
    return LinkedInPostsResponse(total=len(posts), posts=[_post_to_item(p) for p in posts])


@router.patch("/linkedin/{post_id}", response_model=LinkedInPostItem,
              dependencies=[Depends(_require_corp_admin)])
async def edit_linkedin_post(
    post_id: uuid.UUID,
    request: EditPostRequest,
    session: AsyncSession = Depends(get_session),
) -> LinkedInPostItem:
    post = await edit_post(session, post_id, request.content)
    if post is None:
        raise HTTPException(status_code=404, detail="Draft post not found")
    return _post_to_item(post)


@router.post("/linkedin/{post_id}/regenerate", response_model=LinkedInPostItem,
             dependencies=[Depends(_require_corp_admin)])
async def regenerate_linkedin_post(
    post_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> LinkedInPostItem:
    post = await regenerate_post(session, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Draft post not found")
    return _post_to_item(post)


@router.post("/linkedin/{post_id}/publish", response_model=PublishPostResponse,
             dependencies=[Depends(_require_corp_admin)])
async def publish_linkedin_post(
    post_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> PublishPostResponse:
    post, message = await publish_post(session, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    return PublishPostResponse(
        id=str(post.id),
        status=post.status,
        linkedin_post_url=post.linkedin_post_url,
        message=message,
    )


@router.delete("/linkedin/{post_id}",
               dependencies=[Depends(_require_corp_admin)])
async def reject_linkedin_post(
    post_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> dict:
    ok = await reject_post(session, post_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Post not found")
    return {"rejected": True}
