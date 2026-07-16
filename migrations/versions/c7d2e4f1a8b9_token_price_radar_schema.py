"""token_price_radar_schema

Revision ID: c7d2e4f1a8b9
Revises: b3e7f2a1c9d5
Create Date: 2026-07-16 10:00:00.000000

Creates 3 tables for the Token Price Radar pipeline:
  token_price_snapshots          — LLM token price per model per effective date
  token_price_commits_processed  — tracks processed GitHub commits (dedup)
  token_price_reports            — generated report metadata per pipeline run

Retention: permanent — no expires_at, CleanupAgent does not touch these tables.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c7d2e4f1a8b9"
down_revision: Union[str, None] = "b3e7f2a1c9d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "token_price_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("model_id", sa.String(200), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("input_cost_per_token", sa.Float(), nullable=False),
        sa.Column("output_cost_per_token", sa.Float(), nullable=False),
        sa.Column("context_window", sa.Integer(), nullable=True),
        sa.Column("effective_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_commit_sha", sa.String(40), nullable=True),
        sa.Column("source", sa.String(100), nullable=False, server_default=sa.text("'litellm_github'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("model_id", "effective_date", name="uq_token_price_model_date"),
    )
    op.create_index("ix_token_price_snapshots_model_id", "token_price_snapshots", ["model_id"])
    op.create_index("ix_token_price_snapshots_effective_date", "token_price_snapshots", ["effective_date"])
    op.create_index("ix_token_price_snapshots_provider", "token_price_snapshots", ["provider"])

    op.create_table(
        "token_price_commits_processed",
        sa.Column("commit_sha", sa.String(40), primary_key=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "token_price_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("s3_key_json", sa.String(500), nullable=False),
        sa.Column("model_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("snapshot_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("report_schema_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    op.create_index("ix_token_price_reports_generated_at", "token_price_reports", ["generated_at"])


def downgrade() -> None:
    op.drop_table("token_price_reports")
    op.drop_table("token_price_commits_processed")
    op.drop_index("ix_token_price_snapshots_provider", table_name="token_price_snapshots")
    op.drop_index("ix_token_price_snapshots_effective_date", table_name="token_price_snapshots")
    op.drop_index("ix_token_price_snapshots_model_id", table_name="token_price_snapshots")
    op.drop_table("token_price_snapshots")
