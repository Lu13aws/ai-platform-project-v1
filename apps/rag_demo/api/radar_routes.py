from aiplatform.storage.database import get_session
from aiplatform.storage.radar_models import RadarEntry, RadarReport
from apps.rag_demo.api.schemas import RadarEntriesResponse, RadarEntrySchema, RadarReportResponse
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/radar", tags=["radar"])

_CATEGORIES = ["Adopt", "Trial", "Assess", "Hold"]


@router.get("/entries", response_model=RadarEntriesResponse)
async def get_radar_entries(
    category: str | None = Query(default=None, description="Filter by category: Adopt, Trial, Assess, Hold"),
    session: AsyncSession = Depends(get_session),
) -> RadarEntriesResponse:
    """Return all radar entries grouped by category."""
    stmt = select(RadarEntry).order_by(RadarEntry.category, RadarEntry.technology_name)
    if category:
        if category not in _CATEGORIES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid category '{category}'. Must be one of: {', '.join(_CATEGORIES)}",
            )
        stmt = stmt.where(RadarEntry.category == category)

    entries = (await session.scalars(stmt)).all()

    by_category: dict[str, list[RadarEntrySchema]] = {c: [] for c in _CATEGORIES}
    for entry in entries:
        cat = entry.category if entry.category in _CATEGORIES else "Assess"
        by_category[cat].append(RadarEntrySchema.model_validate(entry))

    if category:
        by_category = {category: by_category[category]}

    return RadarEntriesResponse(entry_count=len(entries), entries=by_category)


@router.get("/report/latest", response_model=RadarReportResponse)
async def get_latest_report(
    session: AsyncSession = Depends(get_session),
) -> RadarReportResponse:
    """Return metadata of the most recently generated radar report."""
    report = await session.scalar(
        select(RadarReport).order_by(RadarReport.generated_at.desc()).limit(1)
    )
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No radar reports found — run the pipeline first.",
        )
    return RadarReportResponse.model_validate(report)
