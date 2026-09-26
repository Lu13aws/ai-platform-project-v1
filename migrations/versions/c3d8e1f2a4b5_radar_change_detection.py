"""radar change detection and sentiment

Revision ID: c3d8e1f2a4b5
Revises: b4e2a7c9d5f1
Create Date: 2026-06-17 17:00:00.000000

Adds:
  radar_entries.previous_category  — category from previous pipeline run (for change detection)
  radar_signals.sentiment          — LLM-extracted sentiment per article (positive/neutral/negative)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d8e1f2a4b5"
down_revision: str | None = "b4e2a7c9d5f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "radar_entries",
        sa.Column("previous_category", sa.String(16), nullable=True),
    )
    op.add_column(
        "radar_signals",
        sa.Column("sentiment", sa.String(16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("radar_signals", "sentiment")
    op.drop_column("radar_entries", "previous_category")
