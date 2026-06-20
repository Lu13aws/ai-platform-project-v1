"""
SQLAlchemy ORM models for the Content Creator pipeline.

Tables:
  linkedin_posts  — generated + published LinkedIn posts

Retention:
  linkedin_posts  : 12 months (keep for portfolio history)
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from aiplatform.storage.models import Base


class LinkedInPost(Base):
    __tablename__ = "linkedin_posts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    domain: Mapped[str] = mapped_column(String(20), nullable=False)
    # domain: "technology" | "competitor"
    angle: Mapped[str] = mapped_column(String(20), nullable=False)
    # angle: "product" | "pricing" | "sentiment" | "financial"
    company: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    linkedin_post_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    linkedin_post_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    def __repr__(self) -> str:
        return f"<LinkedInPost domain={self.domain} angle={self.angle} company={self.company} posted_at={self.posted_at}>"
