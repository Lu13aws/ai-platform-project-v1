"""usage_counters

Revision ID: d4f1a9c2e7b3
Revises: c7d2e4f1a8b9
Create Date: 2026-09-26 10:00:00.000000

Daily usage counters that cap LLM-backed public endpoints.
Retention: one row per scope per day (~365/year) — no pruning needed.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4f1a9c2e7b3"
down_revision: Union[str, None] = "c7d2e4f1a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "usage_counters",
        sa.Column("scope", sa.String(50), primary_key=True),
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("usage_counters")
