from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from aiplatform.storage.database import get_session
from apps.knowledge_platform.api.schemas import (
    AgentHeartbeatRequest,
    AgentHeartbeatResponse,
    AgentsResponse,
    IngestSkillRequest,
    IngestSkillResponse,
    QueryRequest,
    QueryResponse,
    RecentActivityResponse,
    ReportsResponse,
    SkillsResponse,
    StatsResponse,
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
