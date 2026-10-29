"""Load intelligence and demand detection API endpoints."""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.load_intelligence import LoadIntelligenceService
from app.schemas.intelligence import (
    IntelligenceOverviewResponse,
    RouteIntelligenceResponse,
    BusIntelligenceResponse,
    ReallocationOpportunityResponse,
)

router = APIRouter()


@router.get(
    "/overview",
    response_model=IntelligenceOverviewResponse,
    summary="Get load intelligence system overview",
)
def get_intelligence_overview(
    db: Session = Depends(get_db),
) -> IntelligenceOverviewResponse:
    """Retrieve system-wide route load classifications and reallocation opportunity count."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection not available",
        )
    return LoadIntelligenceService.get_overview(db)


@router.get(
    "/routes",
    response_model=List[RouteIntelligenceResponse],
    summary="Get route load intelligence assessments",
)
def get_intelligence_routes(
    db: Session = Depends(get_db),
) -> List[RouteIntelligenceResponse]:
    """Retrieve load factors, available capacity, and status assessments for all routes."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection not available",
        )
    return LoadIntelligenceService.get_route_intelligence(db)


@router.get(
    "/buses",
    response_model=List[BusIntelligenceResponse],
    summary="Get bus load intelligence records",
)
def get_intelligence_buses(
    db: Session = Depends(get_db),
) -> List[BusIntelligenceResponse]:
    """Retrieve latest passenger load, available seats, and classification for each bus."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection not available",
        )
    return LoadIntelligenceService.get_bus_intelligence(db)


@router.get(
    "/opportunities",
    response_model=List[ReallocationOpportunityResponse],
    summary="Get potential reallocation opportunities",
)
def get_intelligence_opportunities(
    db: Session = Depends(get_db),
) -> List[ReallocationOpportunityResponse]:
    """Retrieve explainable pairings between overloaded and underutilized routes."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection not available",
        )
    return LoadIntelligenceService.get_opportunities(db)
