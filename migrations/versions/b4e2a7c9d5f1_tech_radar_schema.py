"""tech radar schema

Revision ID: b4e2a7c9d5f1
Revises: 5e289095e7ee
Create Date: 2026-06-17 12:00:00.000000

Adds 5 tables for the Technology Radar pipeline:
  radar_sources  — monitored sources (RSS feeds, blogs)
  raw_articles   — raw fetched content, expires after 30 days
  radar_signals  — LLM-extracted signals per article
  radar_entries  — current radar state per technology (upserted each run)
  radar_reports  — generated report metadata
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b4e2a7c9d5f1"
down_revision: str | None = "5e289095e7ee"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- radar_sources ---
    op.create_table(
        "radar_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("feed_url", sa.String(2048), nullable=True),
        sa.Column("source_type", sa.String(16), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # --- raw_articles ---
    op.create_table(
        "raw_articles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("radar_sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("url", sa.String(2048), nullable=False, unique=True),
        sa.Column("title", sa.String(512), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(128), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_raw_articles_source_id", "raw_articles", ["source_id"])
    op.create_index("ix_raw_articles_expires_at", "raw_articles", ["expires_at"])
    op.create_index(
        "ix_raw_articles_source_hash", "raw_articles", ["source_id", "content_hash"]
    )

    # --- radar_signals ---
    op.create_table(
        "radar_signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("radar_sources.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "article_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("raw_articles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("technology_name", sa.String(256), nullable=False),
        sa.Column("vendor", sa.String(128), nullable=False),
        sa.Column("category", sa.String(16), nullable=False),
        sa.Column("signal_text", sa.Text(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("signal_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_radar_signals_source_id", "radar_signals", ["source_id"])
    op.create_index("ix_radar_signals_article_id", "radar_signals", ["article_id"])
    op.create_index("ix_radar_signals_technology_name", "radar_signals", ["technology_name"])
    op.create_index("ix_radar_signals_vendor", "radar_signals", ["vendor"])
    op.create_index(
        "ix_radar_signals_vendor_category", "radar_signals", ["vendor", "category"]
    )

    # --- radar_entries ---
    op.create_table(
        "radar_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("technology_name", sa.String(256), nullable=False),
        sa.Column("vendor", sa.String(128), nullable=False),
        sa.Column("category", sa.String(16), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("trend", sa.String(16), nullable=False),
        sa.Column("signal_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("technology_name", "vendor", name="uq_radar_entries_tech_vendor"),
    )

    # --- radar_reports ---
    op.create_table(
        "radar_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("s3_key", sa.String(512), nullable=True),
        sa.Column("source_count", sa.Integer(), nullable=False),
        sa.Column("signal_count", sa.Integer(), nullable=False),
        sa.Column("entry_count", sa.Integer(), nullable=False),
        sa.Column("report_schema_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index("ix_radar_reports_generated_at", "radar_reports", ["generated_at"])


def downgrade() -> None:
    op.drop_table("radar_reports")
    op.drop_table("radar_entries")
    op.drop_table("radar_signals")
    op.drop_table("raw_articles")
    op.drop_table("radar_sources")
