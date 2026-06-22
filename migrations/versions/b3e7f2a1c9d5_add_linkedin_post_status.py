"""add_linkedin_post_status

Revision ID: b3e7f2a1c9d5
Revises: f2a9c4e8b1d3
Create Date: 2026-06-22 22:00:00.000000

Adds status column to linkedin_posts for UI review flow.
Values: draft | published | rejected
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b3e7f2a1c9d5"
down_revision: Union[str, None] = "f2a9c4e8b1d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "linkedin_posts",
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
    )
    op.create_index("ix_linkedin_posts_status", "linkedin_posts", ["status"])


def downgrade() -> None:
    op.drop_index("ix_linkedin_posts_status", table_name="linkedin_posts")
    op.drop_column("linkedin_posts", "status")
