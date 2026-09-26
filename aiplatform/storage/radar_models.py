"""
ORM models for the Technology Radar schema.

Tables:
  radar_sources  — monitored sources (RSS feeds, blogs)
  raw_articles   — raw fetched content, expires after 30 days
  radar_signals  — LLM-extracted signals per article (retained 12 months)
  radar_entries  — current state of each technology (upserted each run)
  radar_reports  — generated report metadata (retained 24 months)
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aiplatform.storage.models import Base


class RadarSource(Base):
    __tablename__ = "radar_sources"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    feed_url: Mapped[str | None] = mapped_column(String(2048))
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)  # "rss" | "html"
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    articles: Mapped[list["RawArticle"]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
        lazy="select",
    )
    signals: Mapped[list["RadarSignal"]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
        lazy="select",
    )


class RawArticle(Base):
    __tablename__ = "raw_articles"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("radar_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True)
    title: Mapped[str | None] = mapped_column(String(512))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,  # cleanup agent filters by this
    )

    source: Mapped["RadarSource"] = relationship(back_populates="articles")
    signals: Mapped[list["RadarSignal"]] = relationship(
        back_populates="article",
        lazy="select",
    )

    __table_args__ = (
        Index("ix_raw_articles_source_hash", "source_id", "content_hash"),
    )


class RadarSignal(Base):
    __tablename__ = "radar_signals"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    source_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("radar_sources.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    article_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("raw_articles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    technology_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    vendor: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(16), nullable=False)  # Adopt/Trial/Assess/Hold
    sentiment: Mapped[str | None] = mapped_column(String(16))  # positive/neutral/negative
    signal_text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    signal_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    source: Mapped["RadarSource | None"] = relationship(back_populates="signals")
    article: Mapped["RawArticle | None"] = relationship(back_populates="signals")

    __table_args__ = (
        Index("ix_radar_signals_vendor_category", "vendor", "category"),
    )


class RadarEntry(Base):
    """Current state of each technology — upserted on every pipeline run."""

    __tablename__ = "radar_entries"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    technology_name: Mapped[str] = mapped_column(String(256), nullable=False)
    vendor: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(16), nullable=False)  # Adopt/Trial/Assess/Hold
    previous_category: Mapped[str | None] = mapped_column(String(16))  # snapshot before each run
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    trend: Mapped[str] = mapped_column(String(16), nullable=False)  # up/stable/down
    signal_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        UniqueConstraint("technology_name", "vendor", name="uq_radar_entries_tech_vendor"),
    )


class RadarReport(Base):
    __tablename__ = "radar_reports"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
    )
    s3_key: Mapped[str | None] = mapped_column(String(512))
    source_count: Mapped[int] = mapped_column(Integer, nullable=False)
    signal_count: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_count: Mapped[int] = mapped_column(Integer, nullable=False)
    report_schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
