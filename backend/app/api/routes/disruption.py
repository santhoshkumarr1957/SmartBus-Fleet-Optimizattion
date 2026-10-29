"""Transit Disruption Simulation and Resilience Analysis API endpoints."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.disruption import DisruptionService
from app.schemas.disruption import (
    DisruptionTypeInfo,
    DisruptionSimulationRequest,
    DisruptionSimulationResponse,
    DisruptionScenarioBrief,
)

router = APIRouter()


@router.get(
    "/types",
    response_model=List[DisruptionTypeInfo],
    summary="Get supported transit disruption simulation types",
)
def get_supported_disruption_types() -> List[DisruptionTypeInfo]:
    """Retrieve the catalog of supported disruption simulation types, parameters, and descriptions."""
    return DisruptionService.get_supported_types()


@router.post(
    "/simulate",
    response_model=DisruptionSimulationResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute an isolated transit disruption simulation",
)
def simulate_disruption_scenario(
    request: DisruptionSimulationRequest,
    db: Session = Depends(get_db),
) -> DisruptionSimulationResponse:
    """Execute a rule-based transit disruption simulation on an isolated in-memory snapshot.

    Calculates comparative before-and-after corridor loads, fleet resilience metrics,
    and potential advisory reallocation mitigation options.
    Guaranteed non-mutation: live bus assignments, telemetry, and database records remain unaltered.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection not available",
        )

    try:
        return DisruptionService.simulate_disruption(db=db, request=request)
    except HTTPException:
        raise
    except Exception as exc:
        import logging
        logging.getLogger("uvicorn.error").error(f"Simulation execution error: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Disruption simulation failed: {str(exc)}",
        )


@router.get(
    "/scenarios",
    response_model=List[DisruptionScenarioBrief],
    summary="List recently simulated disruption scenarios",
)
def get_recent_scenarios() -> List[DisruptionScenarioBrief]:
    """Retrieve concise summaries of recently simulated in-memory scenarios."""
    return DisruptionService.get_cached_scenarios()


@router.get(
    "/scenarios/{scenario_id}",
    response_model=DisruptionSimulationResponse,
    summary="Get full calculated impact analysis for a simulated scenario",
)
def get_scenario_impact(
    scenario_id: str = Path(
        ...,
        description="Scenario identifier (e.g. SCEN-BUS_BREAKDOWN-ABC123)",
    ),
) -> DisruptionSimulationResponse:
    """Retrieve full impact analysis, entity comparisons, and resilience metrics for an in-memory scenario."""
    scenario = DisruptionService.get_scenario_by_id(scenario_id)
    if not scenario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Simulated scenario '{scenario_id}' not found in active in-memory cache.",
        )
    return scenario
