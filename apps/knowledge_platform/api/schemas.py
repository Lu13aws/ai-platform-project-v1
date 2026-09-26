from datetime import datetime

from apps.rag_demo.api.schemas import QueryRequest, QueryResponse, SourceReference  # re-export
from pydantic import BaseModel, Field


class StatsResponse(BaseModel):
    documents_indexed: int
    radar_signals: int
    competitor_signals: int
    regulatory_changes: int
    reports_generated: int
    agents_active: int
    skills_indexed: int


class ActivityItem(BaseModel):
    type: str          # "document" | "radar_signal" | "competitor_signal" | "report"
    title: str
    domain: str | None
    timestamp: datetime


class RecentActivityResponse(BaseModel):
    items: list[ActivityItem]


class ReportItem(BaseModel):
    id: str
    domain: str        # "Technology" | "Regulatory" | "Competitor"
    generated_at: datetime
    signal_count: int
    s3_key_html: str | None
    s3_key_json: str | None


class ReportsResponse(BaseModel):
    total: int
    reports: list[ReportItem]


class AgentStatus(BaseModel):
    name: str
    lambda_function: str
    domain: str
    schedule: str
    last_run: datetime | None
    last_indexed: datetime | None = None
    next_run: str
    status: str        # "ok" | "warning" | "unknown"
    last_post_url: str | None = None


class AgentsResponse(BaseModel):
    agents: list[AgentStatus]


class SkillItem(BaseModel):
    document_id: str
    title: str
    source_uri: str
    category: str      # derived from folder path (ai/ aws/ development/ etc.)
    created_at: datetime


class SkillsResponse(BaseModel):
    total: int
    skills: list[SkillItem]


class AgentHeartbeatRequest(BaseModel):
    agent_name: str
    skills_extracted: int = 0
    skills_reindexed: int = 0
    errors: int = 0


class AgentHeartbeatResponse(BaseModel):
    recorded: bool
    agent_name: str


class IngestSkillRequest(BaseModel):
    title: str
    content: str = Field(..., min_length=10)
    source_path: str
    category: str = "other"


class IngestSkillResponse(BaseModel):
    document_id: str
    chunks_created: int
    skipped: bool
    message: str


class LinkedInPostItem(BaseModel):
    id: str
    domain: str
    angle: str
    company: str
    content: str
    status: str
    linkedin_post_url: str | None
    posted_at: datetime | None
    created_at: datetime


class LinkedInPostsResponse(BaseModel):
    total: int
    posts: list[LinkedInPostItem]


class EditPostRequest(BaseModel):
    content: str = Field(..., min_length=10)


class PublishPostResponse(BaseModel):
    id: str
    status: str
    linkedin_post_url: str | None
    message: str


__all__ = [
    "StatsResponse",
    "ActivityItem",
    "RecentActivityResponse",
    "ReportItem",
    "ReportsResponse",
    "AgentStatus",
    "AgentsResponse",
    "SkillItem",
    "SkillsResponse",
    "QueryRequest",
    "QueryResponse",
    "SourceReference",
]
