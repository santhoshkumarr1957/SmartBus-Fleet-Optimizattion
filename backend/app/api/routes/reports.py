"""FastAPI router for TRANSIGHT Stage 10: Reports & Performance Analytics."""
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.report import ReportService
from app.schemas.report import (
    FleetUtilizationReportResponse,
    RoutePerformanceReportResponse,
    DisruptionReportResponse,
    ReallocationReportResponse,
    TrendsReportResponse,
    ReportsOverviewResponse,
)

router = APIRouter()


@router.get(
    "/overview",
    response_model=ReportsOverviewResponse,
    summary="Get consolidated executive reports overview",
)
def get_reports_overview(db: Session = Depends(get_db)) -> ReportsOverviewResponse:
    """Retrieve consolidated overview across fleet utilization, routes, disruptions, and review metrics."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection not available",
        )
    return ReportService.get_overview(db=db)


@router.get(
    "/fleet-utilization",
    response_model=FleetUtilizationReportResponse,
    summary="Get fleet utilization and vehicle asset availability report",
)
def get_fleet_utilization(db: Session = Depends(get_db)) -> FleetUtilizationReportResponse:
    """Retrieve fleet-level seat capacity, operational vehicle ratios, and load factor distribution."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection not available",
        )
    return ReportService.get_fleet_utilization(db=db)


@router.get(
    "/routes",
    response_model=RoutePerformanceReportResponse,
    summary="Get route-level performance comparison report",
)
def get_route_performance(db: Session = Depends(get_db)) -> RoutePerformanceReportResponse:
    """Retrieve route passenger loads, seat capacity headroom, and overcrowding/underutilization ratings."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection not available",
        )
    return ReportService.get_route_performance(db=db)


@router.get(
    "/disruptions",
    response_model=DisruptionReportResponse,
    summary="Get operational disruption audit and simulated scenario analysis",
)
def get_disruptions_analysis(db: Session = Depends(get_db)) -> DisruptionReportResponse:
    """Audit real operational alerts and isolated simulated disruption scenario resilience tests."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection not available",
        )
    return ReportService.get_disruption_analysis(db=db)


@router.get(
    "/reallocation",
    response_model=ReallocationReportResponse,
    summary="Get advisory reallocation proposals and dispatcher review outcomes",
)
def get_reallocation_analysis(db: Session = Depends(get_db)) -> ReallocationReportResponse:
    """Report supervisory advisory recommendations and human dispatcher review determinations."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection not available",
        )
    return ReportService.get_reallocation_analysis(db=db)


@router.get(
    "/trends",
    response_model=TrendsReportResponse,
    summary="Get historical timeseries passenger demand and load factor trends",
)
def get_historical_trends(
    time_range: str = Query("24h", alias="range", description="Historical time window: '1h', '24h', or '7d'"),
    db: Session = Depends(get_db),
) -> TrendsReportResponse:
    """Aggregate recorded passenger loads and vehicle occupancy into deterministic historical time buckets."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection not available",
        )

    # Sanitize query parameter in case invoked directly as Python function
    range_val = time_range if isinstance(time_range, str) else "24h"
    return ReportService.get_historical_trends(db=db, time_range=range_val)


@router.get(
    "/export",
    summary="Export transit performance reports in safe CSV format",
    responses={
        200: {
            "content": {"text/csv": {}},
            "description": "RFC 4180 compliant CSV export file",
        }
    },
)
def export_report_csv(
    report_type: str = Query(..., alias="type", description="Report type: 'fleet', 'routes', 'disruptions', 'reallocation', or 'trends'"),
    time_range: str = Query("24h", alias="range", description="Time window for trends (default: '24h')"),
    export_format: str = Query("csv", alias="format", description="File format ('csv')"),
    db: Session = Depends(get_db),
) -> Response:
    """Export tabular transit operational analytics with stable headers and safe value escaping."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection not available",
        )

    type_val = report_type if isinstance(report_type, str) else ""
    format_val = export_format if isinstance(export_format, str) else "csv"
    range_val = time_range if isinstance(time_range, str) else "24h"

    if format_val.lower() != "csv":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported export format '{format_val}'. Supported format is 'csv'.",
        )

    csv_data = ReportService.export_csv(db=db, report_type=type_val, time_range=range_val)
    ts_label = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"transight_{type_val.lower()}_report_{ts_label}.csv"

    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache, no-store, must-revalidate",
        },
    )
