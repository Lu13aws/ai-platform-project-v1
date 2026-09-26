"""Persistent usage counters. Retention: one row per day (~365/year), no pruning needed."""

from datetime import date

from sqlalchemy import Date, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from aiplatform.storage.models import Base


class UsageCounter(Base):
    __tablename__ = "usage_counters"

    scope: Mapped[str] = mapped_column(String(50), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
