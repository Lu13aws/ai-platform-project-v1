"""
SQLAlchemy ORM models for the Token Price Radar pipeline.

Tables:
  token_price_snapshots          — price point per model per effective date
  token_price_commits_processed  — tracks which GitHub commits have been processed
  token_price_reports            — generated report metadata per pipeline run

Retention: permanent — price history is small and has long-term analytical value.
No expires_at column. CleanupAgent does not touch these tables.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from aiplatform.storage.models import Base


class TokenPriceSnapshot(Base):
    __tablename__ = "token_price_snapshots"
    __table_args__ = (UniqueConstraint("model_id", "effective_date", name="uq_token_price_model_date"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id: Mapped[str] = mapped_column(String(200), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    input_cost_per_token: Mapped[float] = mapped_column(Float, nullable=False)
    output_cost_per_token: Mapped[float] = mapped_column(Float, nullable=False)
    context_window: Mapped[int | None] = mapped_column(Integer, nullable=True)
    effective_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source: Mapped[str] = mapped_column(String(100), nullable=False, default="litellm_github")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class TokenPriceCommitProcessed(Base):
    __tablename__ = "token_price_commits_processed"

    commit_sha: Mapped[str] = mapped_column(String(40), primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class TokenPriceReport(Base):
    __tablename__ = "token_price_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    s3_key_json: Mapped[str] = mapped_column(String(500), nullable=False)
    model_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    snapshot_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    report_schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
