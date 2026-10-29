"""Fleet Reallocation Optimization API endpoints."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.optimization import OptimizationService
from app.services.hybrid_optimization import HybridOptimizationEngine
from app.schemas.optimization import (
    ReallocationRecommendationResponse,
    OptimizationOverviewResponse,
    ReallocationReviewCreate,
    ReallocationReviewResponse,
    ReallocationExecutionCreate,
    ReallocationExecutionResponse,
)
from app.schemas.hybrid_optimization import (
    OptimizationRunRequest,
    OptimizationPlanResponse,
    ScenarioEvaluationRequest,
    ScenarioEvaluationResponse,
)

router = APIRouter()


@router.get(
    "/recommendations",
    response_model=List[ReallocationRecommendationResponse],
    summary="Get rule-based fleet reallocation recommendations",
)
def get_optimization_recommendations(
    target_route_id: Optional[int] = Query(
        None,
        description="Filter recommendations for a specific overloaded target route ID",
    ),
    source_route_id: Optional[int] = Query(
        None,
        description="Filter recommendations for a specific underutilized source route ID",
    ),
    min_score: Optional[float] = Query(
        None,
        ge=0.0,
        le=100.0,
        description="Minimum recommendation suitability score threshold (0.0 to 100.0)",
    ),
    best_only: bool = Query(
        False,
        description="If True, returns only the single highest-scoring candidate bus per route pair",
    ),
    db: Session = Depends(get_db),
) -> List[ReallocationRecommendationResponse]:
    """Retrieve rule-based, advisory fleet reallocation recommendations.

    Analyzes Stage 4 load intelligence to identify overloaded routes (HIGH/CRITICAL)
    and underutilized routes (LOW), evaluates suitable candidate buses with spare capacity,
    considers deadhead distance and operational constraints, and scores recommendations deterministically.

    All recommendations are strictly advisory and require human transit dispatcher confirmation.
    """
    # Normalize FastAPI Query default objects if invoked directly in unit tests
    normalized_target_id = target_route_id if isinstance(target_route_id, int) else None
    normalized_source_id = source_route_id if isinstance(source_route_id, int) else None
    normalized_min_score = min_score if isinstance(min_score, (int, float)) else None
    normalized_best_only = best_only if isinstance(best_only, bool) else False

    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection not available",
        )

    return OptimizationService.generate_recommendations(
        db=db,
        target_route_id=normalized_target_id,
        source_route_id=normalized_source_id,
        min_score=normalized_min_score,
        best_only=normalized_best_only,
    )


@router.get(
    "/overview",
    response_model=OptimizationOverviewResponse,
    summary="Get fleet optimization overview statistics",
)
def get_optimization_overview(
    db: Session = Depends(get_db),
) -> OptimizationOverviewResponse:
    """Retrieve system-wide summary counts of optimization recommendations, priority tiers, and feasibility statuses."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection not available",
        )

    return OptimizationService.get_overview(db)


# -----------------------------------------------------------------------------
# Stage 7: Dispatcher Review & Decision Workflow Endpoints
# -----------------------------------------------------------------------------


@router.post(
    "/recommendations/{recommendation_id}/review",
    response_model=ReallocationReviewResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record dispatcher review decision for a recommendation",
)
def record_dispatcher_review(
    recommendation_id: str = Path(
        ...,
        description="Recommendation unique identifier (e.g. REC-101-202-1)",
    ),
    review_data: ReallocationReviewCreate = ...,
    db: Session = Depends(get_db),
) -> ReallocationReviewResponse:
    """Record a human transit dispatcher decision (APPROVED, REJECTED, or DEFERRED).

    Approval is strictly for operational consideration only.
    No automatic vehicle dispatch or route mutation is performed.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection not available",
        )

    return OptimizationService.record_review(
        db=db,
        recommendation_id=recommendation_id,
        review_data=review_data,
    )


@router.get(
    "/reviews",
    response_model=List[ReallocationReviewResponse],
    summary="Get all historical dispatcher review records",
)
def get_dispatcher_reviews(
    decision: Optional[str] = Query(
        None,
        description="Filter by decision: APPROVED, REJECTED, or DEFERRED",
    ),
    recommendation_id: Optional[str] = Query(
        None,
        description="Filter by specific recommendation identifier",
    ),
    limit: int = Query(
        100,
        ge=1,
        le=500,
        description="Maximum records to return",
    ),
    offset: int = Query(
        0,
        ge=0,
        description="Offset pagination counter",
    ),
    db: Session = Depends(get_db),
) -> List[ReallocationReviewResponse]:
    """Retrieve audit history of all recorded dispatcher review decisions."""
    normalized_decision = decision if isinstance(decision, str) else None
    normalized_rec_id = recommendation_id if isinstance(recommendation_id, str) else None
    normalized_limit = limit if isinstance(limit, int) else 100
    normalized_offset = offset if isinstance(offset, int) else 0

    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection not available",
        )

    return OptimizationService.get_reviews(
        db=db,
        decision=normalized_decision,
        recommendation_id=normalized_rec_id,
        limit=normalized_limit,
        offset=normalized_offset,
    )


@router.get(
    "/recommendations/{recommendation_id}/history",
    response_model=List[ReallocationReviewResponse],
    summary="Get review history for a specific recommendation",
)
def get_recommendation_review_history(
    recommendation_id: str = Path(
        ...,
        description="Recommendation unique identifier (e.g. REC-101-202-1)",
    ),
    db: Session = Depends(get_db),
) -> List[ReallocationReviewResponse]:
    """Retrieve full decision audit history for a single reallocation recommendation."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection not available",
        )

    return OptimizationService.get_recommendation_history(
        db=db,
        recommendation_id=recommendation_id,
    )


# -----------------------------------------------------------------------------
# Dispatcher Execution Workflow Endpoints
# -----------------------------------------------------------------------------


@router.post(
    "/recommendations/{recommendation_id}/execute",
    response_model=ReallocationExecutionResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute an approved fleet reallocation recommendation",
)
def execute_dispatcher_reallocation(
    recommendation_id: str = Path(
        ...,
        description="Recommendation unique identifier (e.g. REC-101-202-202A)",
    ),
    execution_data: ReallocationExecutionCreate = ...,
    db: Session = Depends(get_db),
) -> ReallocationExecutionResponse:
    """Execute an approved fleet reallocation recommendation.

    Verifies dispatcher approval and operational safety constraints,
    updates the bus's persisted route assignment, dispatches runtime
    transfer in the simulator, and records an execution audit log.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection not available",
        )

    return OptimizationService.execute_reassignment(
        db=db,
        recommendation_id=recommendation_id,
        execution_data=execution_data,
    )


@router.get(
    "/executions",
    response_model=List[ReallocationExecutionResponse],
    summary="Get all historical fleet reallocation execution records",
)
def get_reallocation_executions(
    status: Optional[str] = Query(
        None,
        description="Filter by execution status: EXECUTED, IN_PROGRESS, or FAILED",
    ),
    recommendation_id: Optional[str] = Query(
        None,
        description="Filter by specific recommendation identifier",
    ),
    bus_id: Optional[int] = Query(
        None,
        description="Filter by candidate bus ID",
    ),
    limit: int = Query(
        100,
        ge=1,
        le=500,
        description="Maximum records to return",
    ),
    offset: int = Query(
        0,
        ge=0,
        description="Offset pagination counter",
    ),
    db: Session = Depends(get_db),
) -> List[ReallocationExecutionResponse]:
    """Retrieve audit history of all fleet reallocation execution attempts."""
    normalized_status = status if isinstance(status, str) else None
    normalized_rec_id = recommendation_id if isinstance(recommendation_id, str) else None
    normalized_bus_id = bus_id if isinstance(bus_id, int) else None
    normalized_limit = limit if isinstance(limit, int) else 100
    normalized_offset = offset if isinstance(offset, int) else 0

    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection not available",
        )

    return OptimizationService.get_executions(
        db=db,
        recommendation_id=normalized_rec_id,
        bus_id=normalized_bus_id,
        status=normalized_status,
        limit=normalized_limit,
        offset=normalized_offset,
    )


@router.get(
    "/recommendations/{recommendation_id}/executions",
    response_model=List[ReallocationExecutionResponse],
    summary="Get execution history for a specific recommendation",
)
def get_recommendation_executions(
    recommendation_id: str = Path(
        ...,
        description="Recommendation unique identifier (e.g. REC-101-202-202A)",
    ),
    db: Session = Depends(get_db),
) -> List[ReallocationExecutionResponse]:
    """Retrieve execution audit trail for a single reallocation recommendation."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection not available",
        )

    return OptimizationService.get_recommendation_executions(
        db=db,
        recommendation_id=recommendation_id,
    )


# -----------------------------------------------------------------------------
# Phases 1, 2, 5, 6: Hybrid CP-SAT Optimization & Scenario Evaluation Endpoints
# -----------------------------------------------------------------------------

@router.post(
    "/run",
    response_model=OptimizationPlanResponse,
    status_code=status.HTTP_200_OK,
    summary="Run hybrid CP-SAT mathematical fleet optimization",
)
def run_hybrid_fleet_optimization(
    request: Optional[OptimizationRunRequest] = None,
    db: Session = Depends(get_db),
) -> OptimizationPlanResponse:
    """Execute the Google OR-Tools CP-SAT hybrid fleet optimization engine.

    Combines deterministic candidate filtering with mixed-integer constraint programming
    to find the optimal network-wide vehicle reallocation plan balancing overcrowding reduction,
    unmet demand, minimum service coverage, and weather-adjusted travel times.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection not available",
        )
    return HybridOptimizationEngine.run_optimization(db=db, request=request)


@router.get(
    "/latest-plan",
    response_model=Optional[OptimizationPlanResponse],
    summary="Get the most recently computed optimization plan",
)
def get_latest_optimization_plan(
    db: Session = Depends(get_db),
) -> Optional[OptimizationPlanResponse]:
    """Retrieve the latest computed CP-SAT optimization plan or run a fresh one if none exists."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection not available",
        )
    return HybridOptimizationEngine.run_optimization(db=db)


@router.post(
    "/scenarios/evaluate",
    response_model=ScenarioEvaluationResponse,
    summary="Evaluate an isolated resilience 'what-if' scenario",
)
def evaluate_resilience_scenario(
    request: ScenarioEvaluationRequest,
    db: Session = Depends(get_db),
) -> ScenarioEvaluationResponse:
    """Simulate network resilience under combined stress drills without mutating operational records.

    Evaluates simultaneous high demand, bus breakdowns, and severe weather disruptions.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection not available",
        )
    return HybridOptimizationEngine.evaluate_scenario(db=db, request=request)
