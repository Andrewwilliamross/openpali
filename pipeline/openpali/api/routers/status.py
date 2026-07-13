"""Live operational status — explicitly distinct from any release's frozen
source-health claims."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from openpali.storage.models import AcquisitionRun, CurrentRelease, Source

from ..schemas import LiveSourceStatus, LiveStatusResponse
from .releases import get_session

router = APIRouter(prefix="/v1/status", tags=["status"])


@router.get("/sources", response_model=LiveStatusResponse)
def live_sources(session: Session = Depends(get_session)) -> LiveStatusResponse:
    sources = list(session.execute(select(Source)).scalars())
    statuses: list[LiveSourceStatus] = []
    for source in sources:
        last = session.execute(
            select(AcquisitionRun)
            .where(AcquisitionRun.source_id == source.source_id)
            .order_by(AcquisitionRun.requested_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        last_success = session.execute(
            select(func.max(AcquisitionRun.retrieved_at)).where(
                AcquisitionRun.source_id == source.source_id,
                AcquisitionRun.status == "succeeded",
            )
        ).scalar()
        statuses.append(
            LiveSourceStatus(
                source_id=source.source_id,
                last_run_status=last.status if last else None,
                last_attempt_at=last.requested_at if last else None,
                last_success_at=last_success,
                error_class=last.error_class if last else None,
            )
        )
    current = session.get(CurrentRelease, 1)
    return LiveStatusResponse(
        sources=statuses,
        current_release_id=current.current_release_id if current else None,
        lkg_release_id=current.lkg_release_id if current else None,
    )
