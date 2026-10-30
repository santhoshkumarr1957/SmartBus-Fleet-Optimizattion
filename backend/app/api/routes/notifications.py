"""Transit Notifications and Alert Management API endpoints (Stage 9)."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.notification import NotificationService
from app.schemas.notification import (
    NotificationResponse,
    NotificationActionRequest,
    NotificationSummaryResponse,
    NotificationRefreshResponse,
)

router = APIRouter()


@router.get(
    "",
    response_model=List[NotificationResponse],
    summary="List transit operational and simulation alerts",
)
def get_notifications(
    status_filter: Optional[str] = Query(
        None,
        alias="status",
        description="Filter by alert status: ACTIVE, ACKNOWLEDGED, RESOLVED, or ALL",
    ),
    severity_filter: Optional[str] = Query(
        None,
        alias="severity",
        description="Filter by severity level: CRITICAL, HIGH, WARNING, INFO, or ALL",
    ),
    type_filter: Optional[str] = Query(
        None,
        alias="type",
        description="Filter by alert type (e.g. CRITICAL_ROUTE_LOAD, BUS_BREAKDOWN)",
    ),
    source_filter: Optional[str] = Query(
        None,
        alias="source",
        description="Filter by source: LIVE, SIMULATION, or ALL",
    ),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of alerts to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Session = Depends(get_db),
) -> List[NotificationResponse]:
    """Retrieve transit alerts with status, severity, alert type, and source filtering."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection not available",
        )

    status_val = status_filter if isinstance(status_filter, str) else None
    severity_val = severity_filter if isinstance(severity_filter, str) else None
    type_val = type_filter if isinstance(type_filter, str) else None
    source_val = source_filter if isinstance(source_filter, str) else None
    limit_val = limit if isinstance(limit, int) else 50
    offset_val = offset if isinstance(offset, int) else 0

    alerts = NotificationService.get_notifications(
        db=db,
        status_filter=status_val,
        severity_filter=severity_val,
        type_filter=type_val,
        source_filter=source_val,
        limit=limit_val,
        offset=offset_val,
    )
    return [NotificationResponse.model_validate(a) for a in alerts]


@router.get(
    "/summary",
    response_model=NotificationSummaryResponse,
    summary="Get aggregate notification counters",
)
def get_notification_summary(
    db: Session = Depends(get_db),
) -> NotificationSummaryResponse:
    """Retrieve aggregate counts of alerts grouped by status, severity, and source."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection not available",
        )

    try:
        return NotificationService.get_summary(db=db)
    except Exception as exc:
        from app.db.session import sanitize_db_error
        clean_err = sanitize_db_error(str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database query failed: {clean_err}",
        )


@router.post(
    "/{alert_id}/acknowledge",
    response_model=NotificationResponse,
    summary="Acknowledge an active transit alert",
)
def acknowledge_alert(
    alert_id: int = Path(..., description="ID of the alert to acknowledge"),
    payload: Optional[NotificationActionRequest] = None,
    db: Session = Depends(get_db),
) -> NotificationResponse:
    """Acknowledge an active transit alert to indicate dispatcher awareness."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection not available",
        )

    dispatcher_id = payload.dispatcher_id if payload else "DISPATCHER-1"
    notes = payload.notes if payload else None

    alert = NotificationService.acknowledge_alert(
        db=db,
        alert_id=alert_id,
        dispatcher_id=dispatcher_id,
        notes=notes,
    )
    return NotificationResponse.model_validate(alert)


@router.post(
    "/{alert_id}/resolve",
    response_model=NotificationResponse,
    summary="Mark an alert resolved",
)
def resolve_alert(
    alert_id: int = Path(..., description="ID of the alert to resolve"),
    payload: Optional[NotificationActionRequest] = None,
    db: Session = Depends(get_db),
) -> NotificationResponse:
    """Mark an active or acknowledged transit alert as resolved."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection not available",
        )

    dispatcher_id = payload.dispatcher_id if payload else "DISPATCHER-1"
    notes = payload.notes if payload else None

    alert = NotificationService.resolve_alert(
        db=db,
        alert_id=alert_id,
        dispatcher_id=dispatcher_id,
        notes=notes,
    )
    return NotificationResponse.model_validate(alert)


@router.post(
    "/refresh",
    response_model=NotificationRefreshResponse,
    summary="Evaluate operational data and update transit alerts",
)
def refresh_notifications(
    include_simulation: bool = Query(
        True,
        description="Whether to also incorporate cached simulation scenario notices",
    ),
    db: Session = Depends(get_db),
) -> NotificationRefreshResponse:
    """Evaluate current operational conditions across corridors and fleet vehicles.

    Creates alerts for newly detected incidents and updates ongoing alerts with
    strict duplicate suppression.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection not available",
        )

    return NotificationService.evaluate_operational_alerts(
        db=db,
        include_simulation=include_simulation,
    )
