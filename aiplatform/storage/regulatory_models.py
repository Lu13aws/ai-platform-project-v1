"""
ORM models for the Regulatory Radar schema.

Tables:
  regulatory_sources   — monitored regulatory documents (GDPR, EU AI Act, NIST, …)
  regulatory_documents — versioned snapshots: one row per fetched version per source
  regulatory_changes   — detected changes between consecutive versions
  regulatory_reports   — generated report metadata
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aiplatform.storage.models import Base


class RegulatorySource(Base):
    """A regulatory document or framework to monitor (e.g. GDPR, EU AI Act)."""

    __tablename__ = "regulatory_sources"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)  # "html" | "pdf"
    domain: Mapped[str] = mapped_column(String(64), nullable=False)       # Privacy | AI | Cybersecurity | Compliance
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    documents: Mapped[list["RegulatoryDocument"]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
        lazy="select",
        order_by="RegulatoryDocument.fetched_at",
    )
    changes: Mapped[list["RegulatoryChange"]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
        lazy="select",
    )


class RegulatoryDocument(Base):
    """One fetched version of a regulatory source — kept long-term for historical comparison."""

    __tablename__ = "regulatory_documents"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("regulatory_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    s3_key: Mapped[str] = mapped_column(String(512), nullable=False)  # raw file in S3
    text_length: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_latest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
    )

    source: Mapped["RegulatorySource"] = relationship(back_populates="documents")

    __table_args__ = (
        UniqueConstraint("source_id", "content_hash", name="uq_regulatory_docs_source_hash"),
    )


class RegulatoryChange(Base):
    """A detected change between two consecutive versions of a regulatory document."""

    __tablename__ = "regulatory_changes"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("regulatory_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    previous_document_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("regulatory_documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    new_document_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("regulatory_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    diff_summary: Mapped[str] = mapped_column(Text, nullable=False)       # LLM-generated
    impact_level: Mapped[str] = mapped_column(String(16), nullable=False)  # High | Medium | Low
    category: Mapped[str] = mapped_column(String(64), nullable=False)      # Privacy | AI | Cybersecurity | Compliance
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
    )
    report_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("regulatory_reports.id", ondelete="SET NULL"),
        nullable=True,
    )

    source: Mapped["RegulatorySource"] = relationship(back_populates="changes")


class RegulatoryReport(Base):
    """Metadata for a generated regulatory radar report."""

    __tablename__ = "regulatory_reports"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
    )
    s3_key_json: Mapped[str | None] = mapped_column(String(512))
    s3_key_html: Mapped[str | None] = mapped_column(String(512))
    source_count: Mapped[int] = mapped_column(Integer, nullable=False)
    change_count: Mapped[int] = mapped_column(Integer, nullable=False)
    report_schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
