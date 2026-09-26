"""
SQLAlchemy ORM models for the Competitor Radar pipeline.

Tables:
  competitor_sources      — monitored sources per company (blog/pricing/financial/community)
  competitor_raw_content  — raw fetched articles and HN discussions (30-day expiry)
  competitor_signals      — LLM-extracted insights (12-month expiry)
  competitor_reports      — generated report metadata (12-month retention)

Retention:
  competitor_raw_content  : 30 days  (expires_at column, deleted by CleanupAgent)
  competitor_signals      : 12 months (expires_at column, deleted by CleanupAgent)
  competitor_reports      : 12 months (s3 + DB row deleted by CleanupAgent)
  report_id on signals    : SET NULL on report delete — signals kept until their own expires_at
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aiplatform.storage.models import Base


class CompetitorSource(Base):
    __tablename__ = "competitor_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_name: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # source_type: "blog" | "pricing" | "financial" | "community"
    last_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # last_content_hash: used for pricing page change detection
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    raw_content: Mapped[list["CompetitorRawContent"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )
    signals: Mapped[list["CompetitorSignal"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )


class CompetitorRawContent(Base):
    __tablename__ = "competitor_raw_content"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("competitor_sources.id", ondelete="CASCADE"), nullable=False
    )
    url: Mapped[str] = mapped_column(String(1000), nullable=False, unique=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    source: Mapped["CompetitorSource"] = relationship(back_populates="raw_content")
    signals: Mapped[list["CompetitorSignal"]] = relationship(back_populates="raw_content")


class CompetitorSignal(Base):
    __tablename__ = "competitor_signals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("competitor_sources.id", ondelete="CASCADE"), nullable=False
    )
    raw_content_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("competitor_raw_content.id", ondelete="SET NULL"),
        nullable=True,
    )
    report_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("competitor_reports.id", ondelete="SET NULL"),
        nullable=True,
    )
    company_name: Mapped[str] = mapped_column(String(100), nullable=False)
    signal_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # signal_type: product_announcement | pricing_change | financial_update | sentiment_event
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    sentiment: Mapped[str] = mapped_column(String(20), nullable=False)
    # sentiment: positive | neutral | negative
    impact_level: Mapped[str] = mapped_column(String(10), nullable=False)
    # impact_level: High | Medium | Low
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    signal_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    source: Mapped["CompetitorSource"] = relationship(back_populates="signals")
    raw_content: Mapped["CompetitorRawContent | None"] = relationship(back_populates="signals")
    report: Mapped["CompetitorReport | None"] = relationship(back_populates="signals")


class CompetitorReport(Base):
    __tablename__ = "competitor_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    s3_key_json: Mapped[str] = mapped_column(String(500), nullable=False)
    s3_key_html: Mapped[str] = mapped_column(String(500), nullable=False)
    company_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    signal_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    report_schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    signals: Mapped[list["CompetitorSignal"]] = relationship(back_populates="report")
