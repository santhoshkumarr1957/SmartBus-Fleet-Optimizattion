"""Bus Breakdown Management API endpoints (Phase 4)."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.breakdown import BreakdownService
from app.schemas.breakdown import (
    BreakdownReportRequest,
    BreakdownStatusUpdateRequest,
    BreakdownResponse,
    BreakdownSummaryResponse,
    ReplacementCandidateResponse,
)

router = APIRouter()


@router.get(
    "",
    response_model=List[BreakdownResponse],
    summary="Get all reported bus breakdown incidents",
)
def get_breakdowns(
    active_only: bool = Query(
        False, description="If True, only returns unresolved incidents (REPORTED, CONFIRMED, UNDER_REPAIR)"
    ),
    db: Session = Depends(get_db),
) -> List[BreakdownResponse]:
    """Retrieve history or active list of bus breakdown incidents."""
    return BreakdownService.get_breakdowns(db=db, active_only=active_only)


@router.get(
    "/summary",
    response_model=BreakdownSummaryResponse,
    summary="Get fleet breakdown summary and capacity impacts",
)
def get_breakdown_summary(
    db: Session = Depends(get_db),
) -> BreakdownSummaryResponse:
    """Consolidated overview of fleet availability percentage, active breakdowns, and capacity lost."""
    return BreakdownService.get_breakdown_summary(db=db)


@router.post(
    "",
    response_model=BreakdownResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Report a vehicle breakdown incident",
)
def report_breakdown(
    request: BreakdownReportRequest,
    db: Session = Depends(get_db),
) -> BreakdownResponse:
    """Report a bus breakdown. Immediately removes bus from active fleet and halts movement in simulator."""
    return BreakdownService.report_breakdown(db=db, request=request)


@router.put(
    "/{incident_id}/status",
    response_model=BreakdownResponse,
    summary="Update breakdown incident lifecycle status",
)
def update_breakdown_status(
    incident_id: int = Path(..., description="Breakdown incident ID"),
    request: BreakdownStatusUpdateRequest = ...,
    db: Session = Depends(get_db),
) -> BreakdownResponse:
    """Advance breakdown lifecycle: REPORTED -> CONFIRMED -> UNDER_REPAIR -> AVAILABLE.

    Setting status to AVAILABLE marks vehicle repaired and restores active service.
    """
    return BreakdownService.update_status(db=db, incident_id=incident_id, request=request)


@router.get(
    "/{bus_id}/replacement-candidates",
    response_model=ReplacementCandidateResponse,
    summary="Evaluate replacement bus candidates for a broken-down vehicle",
)
def get_replacement_candidates(
    bus_id: int = Path(..., description="ID of the broken-down bus"),
    db: Session = Depends(get_db),
) -> ReplacementCandidateResponse:
    """Evaluate feasible donor buses to replace a broken-down vehicle while respecting minimum service coverage."""
    return BreakdownService.get_replacement_candidates(db=db, broken_bus_id=bus_id)
