"""
Change Detection Agent — identifies what moved in the radar since the last pipeline run.

Reads radar_entries after the Analyzer has run and classifies each entry as:
  - new      : previous_category IS NULL  (first time seen)
  - moved_up : category rank increased    (e.g. Assess → Trial)
  - moved_down: category rank decreased   (e.g. Trial → Assess)
  - unchanged: category == previous_category

The pipeline handler must run a snapshot step BEFORE the Collector:
  UPDATE radar_entries SET previous_category = category
This ensures previous_category reflects last week's state, and new entries
inserted by the Analyzer this run will have previous_category = NULL.
"""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aiplatform.storage.radar_models import RadarEntry

_CATEGORY_RANK = {"Adopt": 3, "Trial": 2, "Assess": 1, "Hold": 0}


@dataclass
class EntryChange:
    technology_name: str
    vendor: str
    previous_category: str | None
    current_category: str
    change_type: str  # "new" | "moved_up" | "moved_down"

    def label(self) -> str:
        if self.change_type == "new":
            return f"★ NEW  {self.technology_name} ({self.vendor}) → {self.current_category}"
        arrow = "↑" if self.change_type == "moved_up" else "↓"
        return f"{arrow} {self.technology_name} ({self.vendor})  {self.previous_category} → {self.current_category}"


@dataclass
class ChangeReport:
    new_entries: list[EntryChange] = field(default_factory=list)
    moved_up: list[EntryChange] = field(default_factory=list)
    moved_down: list[EntryChange] = field(default_factory=list)
    unchanged: int = 0

    def has_changes(self) -> bool:
        return bool(self.new_entries or self.moved_up or self.moved_down)

    def total_changes(self) -> int:
        return len(self.new_entries) + len(self.moved_up) + len(self.moved_down)

    def summary_lines(self) -> list[str]:
        lines = []
        for e in self.new_entries:
            lines.append(e.label())
        for e in self.moved_up:
            lines.append(e.label())
        for e in self.moved_down:
            lines.append(e.label())
        return lines

    def __str__(self) -> str:
        return (
            f"new={len(self.new_entries)} "
            f"moved_up={len(self.moved_up)} "
            f"moved_down={len(self.moved_down)} "
            f"unchanged={self.unchanged}"
        )


class ChangeDetectionAgent:
    async def run(self, session: AsyncSession) -> ChangeReport:
        report = ChangeReport()

        entries = (await session.scalars(select(RadarEntry))).all()

        for entry in entries:
            prev = entry.previous_category
            curr = entry.category

            if prev is None:
                change = EntryChange(
                    technology_name=entry.technology_name,
                    vendor=entry.vendor,
                    previous_category=None,
                    current_category=curr,
                    change_type="new",
                )
                report.new_entries.append(change)
            elif prev == curr:
                report.unchanged += 1
            else:
                prev_rank = _CATEGORY_RANK.get(prev, 1)
                curr_rank = _CATEGORY_RANK.get(curr, 1)
                change_type = "moved_up" if curr_rank > prev_rank else "moved_down"
                change = EntryChange(
                    technology_name=entry.technology_name,
                    vendor=entry.vendor,
                    previous_category=prev,
                    current_category=curr,
                    change_type=change_type,
                )
                if change_type == "moved_up":
                    report.moved_up.append(change)
                else:
                    report.moved_down.append(change)

        print(f"  [changes] {report}")
        return report
