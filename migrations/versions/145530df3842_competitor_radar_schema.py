"""competitor_radar_schema

Revision ID: 145530df3842
Revises: e5a1b3c7d9f2
Create Date: 2026-06-19 13:01:46.342497

Creates 4 tables for the Competitor Radar pipeline:
  competitor_sources      — monitored sources per company
  competitor_raw_content  — raw fetched articles / HN discussions (30-day expiry)
  competitor_signals      — LLM-extracted insights (12-month expiry)
  competitor_reports      — generated report metadata (12-month retention)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "145530df3842"
down_revision: str | None = "e5a1b3c7d9f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "competitor_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_name", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("url", sa.String(500), nullable=False, unique=True),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("last_content_hash", sa.String(64), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # competitor_reports created BEFORE competitor_signals due to FK dependency
    op.create_table(
        "competitor_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("s3_key_json", sa.String(500), nullable=False),
        sa.Column("s3_key_html", sa.String(500), nullable=False),
        sa.Column("company_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("signal_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("report_schema_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    op.create_index("ix_competitor_reports_generated_at", "competitor_reports", ["generated_at"])

    op.create_table(
        "competitor_raw_content",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("competitor_sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("url", sa.String(1000), nullable=False, unique=True),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_competitor_raw_content_source_id", "competitor_raw_content", ["source_id"])
    op.create_index("ix_competitor_raw_content_processed_at", "competitor_raw_content", ["processed_at"])
    op.create_index("ix_competitor_raw_content_expires_at", "competitor_raw_content", ["expires_at"])

    op.create_table(
        "competitor_signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("competitor_sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "raw_content_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("competitor_raw_content.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "report_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("competitor_reports.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("company_name", sa.String(100), nullable=False),
        sa.Column("signal_type", sa.String(30), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("sentiment", sa.String(20), nullable=False),
        sa.Column("impact_level", sa.String(10), nullable=False),
        sa.Column("url", sa.String(1000), nullable=True),
        sa.Column("signal_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_competitor_signals_source_id", "competitor_signals", ["source_id"])
    op.create_index("ix_competitor_signals_company_name", "competitor_signals", ["company_name"])
    op.create_index("ix_competitor_signals_signal_date", "competitor_signals", ["signal_date"])
    op.create_index("ix_competitor_signals_expires_at", "competitor_signals", ["expires_at"])
    op.create_index("ix_competitor_signals_report_id", "competitor_signals", ["report_id"])


def downgrade() -> None:
    op.drop_table("competitor_signals")
    op.drop_table("competitor_raw_content")
    op.drop_table("competitor_reports")
    op.drop_table("competitor_sources")
