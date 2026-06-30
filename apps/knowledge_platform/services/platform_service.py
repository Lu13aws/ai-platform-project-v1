"""
Aggregate queries across all platform schemas for the Knowledge Platform dashboard.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aiplatform.ingestion.chunker import Chunker
from aiplatform.ingestion.deduplication import content_changed, hash_content
from aiplatform.llm import get_llm_provider
from aiplatform.retrieval.embedder import Embedder
from aiplatform.storage.competitor_models import CompetitorReport, CompetitorSignal
from aiplatform.storage.content_models import LinkedInPost
from aiplatform.storage.models import Chunk, Document, Embedding
from aiplatform.storage.radar_models import RadarReport, RadarSignal
from aiplatform.storage.regulatory_models import RegulatoryChange, RegulatoryReport
from apps.knowledge_platform.api.schemas import (
    ActivityItem,
    AgentHeartbeatRequest,
    AgentHeartbeatResponse,
    AgentStatus,
    IngestSkillRequest,
    IngestSkillResponse,
    ReportItem,
    SkillItem,
)

# Hardcoded agent registry — matches EventBridge schedules in AWS
_AGENT_REGISTRY = [
    {
        "name": "Tech Radar Pipeline",
        "lambda_function": "ai-platform-radar-pipeline",
        "domain": "Technology",
        "schedule": "Monday 06:00 UTC",
        "report_table": "radar",
        "warning_days": 8,
        "index_prefix": "skill://radar/",
    },
    {
        "name": "Regulatory Radar Pipeline",
        "lambda_function": "ai-platform-regulatory-pipeline",
        "domain": "Regulatory",
        "schedule": "1st of month 07:00 UTC",
        "report_table": "regulatory",
        "warning_days": 35,
        "index_prefix": "skill://regulatory/",
    },
    {
        "name": "Competitor Radar Pipeline",
        "lambda_function": "ai-platform-competitor-pipeline",
        "domain": "Competitor",
        "schedule": "Monday 08:00 UTC",
        "report_table": "competitor",
        "warning_days": 8,
        "index_prefix": "skill://competitor/",
    },
    {
        "name": "Cleanup Agent",
        "lambda_function": "ai-platform-cleanup",
        "domain": "Platform",
        "schedule": "1st of month 03:00 UTC",
        "report_table": None,
        "warning_days": None,
        "index_prefix": None,
    },
    {
        "name": "RAG Demo API",
        "lambda_function": "ai-platform-rag-demo",
        "domain": "RAG",
        "schedule": "On-demand",
        "report_table": None,
        "warning_days": None,
        "index_prefix": None,
    },
    {
        "name": "Skill Extraction Agent",
        "lambda_function": "local-script",
        "domain": "Skills",
        "schedule": "On-demand",
        "report_table": "heartbeat",
        "warning_days": None,
        "index_prefix": None,
    },
    {
        "name": "LinkedIn Publisher",
        "lambda_function": "ai-platform-content-creator",
        "domain": "Content",
        "schedule": "Tuesday 08:30 UTC",
        "report_table": "linkedin",
        "warning_days": 8,
        "index_prefix": None,
    },
]

_HEARTBEAT_APP = "agent_heartbeat"


async def get_stats(session: AsyncSession) -> dict:
    doc_count = await session.scalar(select(func.count()).select_from(Document))
    radar_signal_count = await session.scalar(select(func.count()).select_from(RadarSignal))
    competitor_signal_count = await session.scalar(select(func.count()).select_from(CompetitorSignal))
    regulatory_change_count = await session.scalar(select(func.count()).select_from(RegulatoryChange))

    radar_report_count = await session.scalar(select(func.count()).select_from(RadarReport))
    regulatory_report_count = await session.scalar(select(func.count()).select_from(RegulatoryReport))
    competitor_report_count = await session.scalar(select(func.count()).select_from(CompetitorReport))

    skills_count = await session.scalar(
        select(func.count())
        .select_from(Document)
        .where(Document.app_name == "skills_hub")
    )

    return {
        "documents_indexed": (doc_count or 0) - (skills_count or 0),
        "radar_signals": radar_signal_count or 0,
        "competitor_signals": competitor_signal_count or 0,
        "regulatory_changes": regulatory_change_count or 0,
        "reports_generated": (radar_report_count or 0) + (regulatory_report_count or 0) + (competitor_report_count or 0),
        "agents_active": len(_AGENT_REGISTRY),
        "skills_indexed": skills_count or 0,
    }


async def get_recent_activity(session: AsyncSession, limit: int = 20) -> list[ActivityItem]:
    items: list[ActivityItem] = []

    # Last ingested documents (excluding skills_hub)
    docs = await session.scalars(
        select(Document)
        .where(Document.app_name != "skills_hub")
        .order_by(Document.created_at.desc())
        .limit(5)
    )
    for doc in docs:
        items.append(ActivityItem(
            type="document",
            title=doc.title or doc.source_uri,
            domain=doc.app_name,
            timestamp=doc.created_at,
        ))

    # Last radar signals
    signals = await session.scalars(
        select(RadarSignal).order_by(RadarSignal.created_at.desc()).limit(5)
    )
    for sig in signals:
        items.append(ActivityItem(
            type="radar_signal",
            title=f"{sig.technology_name} ({sig.vendor}) → {sig.category}",
            domain="Technology",
            timestamp=sig.created_at,
        ))

    # Last competitor signals
    comp_signals = await session.scalars(
        select(CompetitorSignal).order_by(CompetitorSignal.signal_date.desc()).limit(5)
    )
    for sig in comp_signals:
        items.append(ActivityItem(
            type="competitor_signal",
            title=f"{sig.company_name}: {sig.title}",
            domain="Competitor",
            timestamp=sig.signal_date,
        ))

    # Last reports (all domains)
    radar_reports = await session.scalars(
        select(RadarReport).order_by(RadarReport.generated_at.desc()).limit(3)
    )
    for r in radar_reports:
        items.append(ActivityItem(
            type="report",
            title="Technology Radar Report",
            domain="Technology",
            timestamp=r.generated_at,
        ))

    comp_reports = await session.scalars(
        select(CompetitorReport).order_by(CompetitorReport.generated_at.desc()).limit(3)
    )
    for r in comp_reports:
        items.append(ActivityItem(
            type="report",
            title="Competitor Radar Report",
            domain="Competitor",
            timestamp=r.generated_at,
        ))

    reg_reports = await session.scalars(
        select(RegulatoryReport).order_by(RegulatoryReport.generated_at.desc()).limit(3)
    )
    for r in reg_reports:
        items.append(ActivityItem(
            type="report",
            title="Regulatory Radar Report",
            domain="Regulatory",
            timestamp=r.generated_at,
        ))

    items.sort(key=lambda x: x.timestamp, reverse=True)
    return items[:limit]


async def get_all_reports(session: AsyncSession) -> list[ReportItem]:
    items: list[ReportItem] = []

    radar_reports = await session.scalars(
        select(RadarReport).order_by(RadarReport.generated_at.desc())
    )
    for r in radar_reports:
        html_key = r.s3_key.replace(".json", ".html") if r.s3_key else None
        items.append(ReportItem(
            id=str(r.id),
            domain="Technology",
            generated_at=r.generated_at,
            signal_count=r.signal_count,
            s3_key_html=html_key,
            s3_key_json=r.s3_key,
        ))

    comp_reports = await session.scalars(
        select(CompetitorReport).order_by(CompetitorReport.generated_at.desc())
    )
    for r in comp_reports:
        items.append(ReportItem(
            id=str(r.id),
            domain="Competitor",
            generated_at=r.generated_at,
            signal_count=r.signal_count,
            s3_key_html=r.s3_key_html,
            s3_key_json=r.s3_key_json,
        ))

    reg_reports = await session.scalars(
        select(RegulatoryReport).order_by(RegulatoryReport.generated_at.desc())
    )
    for r in reg_reports:
        items.append(ReportItem(
            id=str(r.id),
            domain="Regulatory",
            generated_at=r.generated_at,
            signal_count=r.change_count,
            s3_key_html=r.s3_key_html,
            s3_key_json=r.s3_key_json,
        ))

    items.sort(key=lambda x: x.generated_at, reverse=True)
    return items


async def get_agent_statuses(session: AsyncSession) -> list[AgentStatus]:
    # Fetch last run dates from report tables
    last_radar = await session.scalar(
        select(func.max(RadarReport.generated_at))
    )
    last_competitor = await session.scalar(
        select(func.max(CompetitorReport.generated_at))
    )
    last_regulatory = await session.scalar(
        select(func.max(RegulatoryReport.generated_at))
    )

    last_heartbeat = await session.scalar(
        select(func.max(Document.updated_at)).where(
            Document.app_name == _HEARTBEAT_APP
        )
    )

    last_linkedin_row = await session.execute(
        select(LinkedInPost.posted_at, LinkedInPost.linkedin_post_url)
        .where(LinkedInPost.posted_at.isnot(None))
        .order_by(LinkedInPost.posted_at.desc())
        .limit(1)
    )
    linkedin_row = last_linkedin_row.first()
    last_linkedin = linkedin_row[0] if linkedin_row else None
    last_linkedin_url = linkedin_row[1] if linkedin_row else None

    last_runs = {
        "radar": last_radar,
        "regulatory": last_regulatory,
        "competitor": last_competitor,
        "heartbeat": last_heartbeat,
        "linkedin": last_linkedin,
    }

    now = datetime.now(UTC)

    statuses: list[AgentStatus] = []
    for agent in _AGENT_REGISTRY:
        last_run = last_runs.get(agent["report_table"]) if agent["report_table"] else None
        warning_days = agent.get("warning_days")

        if last_run is None:
            status = "unknown"
        elif warning_days is None:
            status = "ok"  # on-demand: any recorded run = ok
        elif (now - last_run) <= timedelta(days=warning_days):
            status = "ok"
        else:
            status = "warning"

        last_post_url = last_linkedin_url if agent["report_table"] == "linkedin" else None

        last_indexed: datetime | None = None
        index_prefix = agent.get("index_prefix")
        if index_prefix:
            last_indexed = await session.scalar(
                select(func.max(Document.updated_at)).where(
                    Document.source_uri.like(f"{index_prefix}%")
                )
            )

        statuses.append(AgentStatus(
            name=agent["name"],
            lambda_function=agent["lambda_function"],
            domain=agent["domain"],
            schedule=agent["schedule"],
            last_run=last_run,
            last_indexed=last_indexed,
            next_run=agent["schedule"],
            status=status,
            last_post_url=last_post_url,
        ))

    return statuses


async def get_skills(session: AsyncSession) -> list[SkillItem]:
    docs = await session.scalars(
        select(Document)
        .where(Document.app_name == "skills_hub")
        .order_by(Document.title)
    )

    skills: list[SkillItem] = []
    for doc in docs:
        # Use stored metadata category; fall back to path parsing for legacy docs
        category = (doc.doc_metadata or {}).get("category") or "other"

        skills.append(SkillItem(
            document_id=str(doc.id),
            title=doc.title or doc.source_uri,
            source_uri=doc.source_uri,
            category=category,
            created_at=doc.created_at,
        ))

    return skills


async def ingest_skill(session: AsyncSession, request: IngestSkillRequest) -> IngestSkillResponse:
    """Ingest a skill from raw markdown content — no file access needed."""
    from sqlalchemy import delete as sql_delete

    content_hash = hash_content(request.content)
    source_uri = f"skill://{request.source_path}"

    # Dedup by source_uri
    existing = await session.scalar(
        select(Document).where(
            Document.source_uri == source_uri,
            Document.app_name == "skills_hub",
        )
    )
    if existing is not None:
        if not content_changed(content_hash, existing.content_hash):
            return IngestSkillResponse(
                document_id=str(existing.id),
                chunks_created=0,
                skipped=True,
                message="Skill unchanged — skipped.",
            )
        await session.execute(sql_delete(Document).where(Document.id == existing.id))
        await session.flush()

    # Dedup by content hash (same content with a different source_uri — e.g. repeated pipeline
    # runs that produce identical report data under a new timestamped S3 key).
    existing_by_hash = await session.scalar(
        select(Document).where(Document.content_hash == content_hash)
    )
    if existing_by_hash is not None:
        return IngestSkillResponse(
            document_id=str(existing_by_hash.id),
            chunks_created=0,
            skipped=True,
            message="Content unchanged — skipped.",
        )

    # Chunk
    chunker = Chunker()
    chunks = chunker.split(
        request.content,
        metadata={"category": request.category, "skill_name": request.title},
    )

    # Embed
    provider = get_llm_provider()
    embedder = Embedder(provider)
    embedding_responses = await embedder.embed_chunks(chunks)

    # Store
    doc_id = uuid4()
    session.add(Document(
        id=doc_id,
        source_uri=source_uri,
        content_hash=content_hash,
        title=request.title,
        mime_type="text/markdown",
        doc_metadata={"category": request.category, "source_path": request.source_path},
        app_name="skills_hub",
    ))
    await session.flush()

    chunk_ids = []
    for chunk in chunks:
        cid = uuid4()
        chunk_ids.append(cid)
        session.add(Chunk(
            id=cid,
            document_id=doc_id,
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            content_hash=hash_content(chunk.content),
            token_count=chunk.token_count,
            chunk_metadata=chunk.metadata,
        ))

    await session.flush()

    for cid, emb in zip(chunk_ids, embedding_responses):
        session.add(Embedding(
            id=uuid4(),
            chunk_id=cid,
            vector=emb.vector,
            model=emb.model,
            provider=emb.provider.value,
        ))

    return IngestSkillResponse(
        document_id=str(doc_id),
        chunks_created=len(chunks),
        skipped=False,
        message=f"Ingested skill '{request.title}' ({len(chunks)} chunks).",
    )


async def record_heartbeat(session: AsyncSession, request: AgentHeartbeatRequest) -> AgentHeartbeatResponse:
    from sqlalchemy import delete as sql_delete

    source_uri = f"heartbeat://{request.agent_name}"
    # Remove old heartbeat record so updated_at reflects the latest run
    await session.execute(
        sql_delete(Document).where(
            Document.source_uri == source_uri,
            Document.app_name == _HEARTBEAT_APP,
        )
    )
    await session.flush()

    session.add(Document(
        id=uuid4(),
        source_uri=source_uri,
        content_hash=hash_content(
            f"{request.agent_name}:{request.skills_extracted}:{request.skills_reindexed}"
        ),
        title=f"Heartbeat: {request.agent_name}",
        mime_type="application/json",
        doc_metadata={
            "skills_extracted": request.skills_extracted,
            "skills_reindexed": request.skills_reindexed,
            "errors": request.errors,
        },
        app_name=_HEARTBEAT_APP,
    ))
    return AgentHeartbeatResponse(recorded=True, agent_name=request.agent_name)
