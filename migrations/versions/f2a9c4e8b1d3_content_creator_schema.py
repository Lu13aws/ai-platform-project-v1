"""content_creator_schema

Revision ID: f2a9c4e8b1d3
Revises: 145530df3842
Create Date: 2026-06-20 17:00:00.000000

Creates table for the Content Creator pipeline:
  linkedin_posts  — generated and published LinkedIn posts (12-month retention)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f2a9c4e8b1d3"
down_revision: str | None = "145530df3842"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "linkedin_posts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("domain", sa.String(20), nullable=False),
        sa.Column("angle", sa.String(20), nullable=False),
        sa.Column("company", sa.String(100), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("linkedin_post_id", sa.String(200), nullable=True),
        sa.Column("linkedin_post_url", sa.String(500), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_linkedin_posts_posted_at", "linkedin_posts", ["posted_at"])
    op.create_index("ix_linkedin_posts_domain", "linkedin_posts", ["domain"])


def downgrade() -> None:
    op.drop_table("linkedin_posts")
