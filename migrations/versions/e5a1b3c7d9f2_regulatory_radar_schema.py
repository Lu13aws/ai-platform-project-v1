"""regulatory radar schema

Revision ID: e5a1b3c7d9f2
Revises: c3d8e1f2a4b5
Create Date: 2026-06-19 09:00:00.000000

Adds 4 tables for the Regulatory Radar pipeline:
  regulatory_sources   — monitored regulatory documents (GDPR, EU AI Act, NIST, …)
  regulatory_documents — versioned snapshots per source (kept long-term)
  regulatory_changes   — LLM-analyzed changes between versions
  regulatory_reports   — generated report metadata
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e5a1b3c7d9f2"
down_revision: Union[str, None] = "c3d8e1f2a4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- regulatory_sources ---
    op.create_table(
        "regulatory_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False, unique=True),
        sa.Column("source_type", sa.String(16), nullable=False),
        sa.Column("domain", sa.String(64), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # --- regulatory_reports (created before changes due to FK) ---
    op.create_table(
        "regulatory_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("s3_key_json", sa.String(512), nullable=True),
        sa.Column("s3_key_html", sa.String(512), nullable=True),
        sa.Column("source_count", sa.Integer(), nullable=False),
        sa.Column("change_count", sa.Integer(), nullable=False),
        sa.Column("report_schema_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index("ix_regulatory_reports_generated_at", "regulatory_reports", ["generated_at"])

    # --- regulatory_documents ---
    op.create_table(
        "regulatory_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("regulatory_sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content_hash", sa.String(128), nullable=False),
        sa.Column("s3_key", sa.String(512), nullable=False),
        sa.Column("text_length", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_latest", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_id", "content_hash", name="uq_regulatory_docs_source_hash"),
    )
    op.create_index("ix_regulatory_documents_source_id", "regulatory_documents", ["source_id"])
    op.create_index("ix_regulatory_documents_is_latest", "regulatory_documents", ["is_latest"])
    op.create_index("ix_regulatory_documents_fetched_at", "regulatory_documents", ["fetched_at"])

    # --- regulatory_changes ---
    op.create_table(
        "regulatory_changes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("regulatory_sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "previous_document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("regulatory_documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "new_document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("regulatory_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("diff_summary", sa.Text(), nullable=False),
        sa.Column("impact_level", sa.String(16), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "report_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("regulatory_reports.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_regulatory_changes_source_id", "regulatory_changes", ["source_id"])
    op.create_index("ix_regulatory_changes_detected_at", "regulatory_changes", ["detected_at"])


def downgrade() -> None:
    op.drop_table("regulatory_changes")
    op.drop_table("regulatory_documents")
    op.drop_table("regulatory_reports")
    op.drop_table("regulatory_sources")
