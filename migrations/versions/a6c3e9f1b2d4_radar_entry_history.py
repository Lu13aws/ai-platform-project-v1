"""radar entry history

Revision ID: a6c3e9f1b2d4
Revises: d4f1a9c2e7b3
Create Date: 2026-10-27 09:30:00.000000

Adds:
  radar_entry_history — category of every radar entry per pipeline run (Phase 7 movement history)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a6c3e9f1b2d4"
down_revision: str | None = "d4f1a9c2e7b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "radar_entry_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_date", sa.Date(), nullable=False),
        sa.Column("technology_name", sa.String(256), nullable=False),
        sa.Column("vendor", sa.String(128), nullable=False),
        sa.Column("category", sa.String(16), nullable=False),
        sa.Column("previous_category", sa.String(16), nullable=True),
        sa.Column("trend", sa.String(16), nullable=True),
        sa.Column("signal_count", sa.Integer(), nullable=True),
        sa.Column("origin", sa.String(16), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "technology_name", "vendor", "run_date", name="uq_radar_entry_history_tech_vendor_date"
        ),
    )
    op.create_index("ix_radar_entry_history_run_date", "radar_entry_history", ["run_date"])


def downgrade() -> None:
    op.drop_index("ix_radar_entry_history_run_date", table_name="radar_entry_history")
    op.drop_table("radar_entry_history")
