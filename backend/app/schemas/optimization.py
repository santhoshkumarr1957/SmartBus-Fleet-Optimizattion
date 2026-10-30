"""Optimization schemas for Fleet Reallocation recommendations and Dispatcher Reviews.

Defines Pydantic models for advisory bus reallocation recommendations,
candidate bus details, scoring, operational limitations, and Stage 7
dispatcher review approval workflows.
"""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class RouteBrief(BaseModel):
    """Concise representation of a route within a recommendation."""

    route_id: int
    route_number: str
    name: Optional[str] = None
    load_factor: float
    status: str

    model_config = ConfigDict(from_attributes=True)


class BusBrief(BaseModel):
    """Concise representation of a candidate bus within a recommendation."""

    bus_id: int
    bus_number: str
    capacity: int
    current_occupancy: int
    available_capacity: int
    load_factor: float

    model_config = ConfigDict(from_attributes=True)


class ManualReassignmentCreate(BaseModel):
    """Schema for manual route assignment by a dispatcher."""

    target_route_id: int = Field(
        ...,
        description="ID of the target route to assign the bus to",
    )
    dispatcher_id: Optional[str] = Field(
        default="DISPATCHER-1",
        description="Identifier of the executing dispatcher",
    )
    reason: Optional[str] = Field(
        default=None,
        description="Operational justification for the route reassignment",
    )


class ReallocationExecutionCreate(BaseModel):
    """Schema for executing an approved fleet reallocation recommendation."""

    dispatcher_id: Optional[str] = Field(
        default="DISPATCHER-1",
        description="Identifier of the executing dispatcher",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Optional operational justification or execution notes",
    )


class ReallocationExecutionResponse(BaseModel):
    """Schema representing an executed fleet reallocation dispatch."""

    id: int
    recommendation_id: str
    review_id: Optional[int] = None
    bus_id: int
    bus_number: str
    source_route_id: int
    source_route_number: str
    target_route_id: int
    target_route_number: str
    dispatcher_id: str
    status: str
    error_message: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReallocationReviewCreate(BaseModel):
    """Schema for submitting a dispatcher review decision."""

    decision: str = Field(
        ...,
        description="Dispatcher review decision: APPROVED, REJECTED, or DEFERRED",
        examples=["APPROVED", "REJECTED", "DEFERRED"],
    )
    dispatcher_id: Optional[str] = Field(
        default="DISPATCHER-1",
        description="Identifier of the reviewing dispatcher",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Optional operational justification or dispatch remarks",
    )
    target_route_id: Optional[int] = Field(default=None, description="Optional target route ID")
    target_route_number: Optional[str] = Field(default=None, description="Optional target route number")
    source_route_id: Optional[int] = Field(default=None, description="Optional source route ID")
    source_route_number: Optional[str] = Field(default=None, description="Optional source route number")
    candidate_bus_id: Optional[int] = Field(default=None, description="Optional candidate bus ID")
    candidate_bus_number: Optional[str] = Field(default=None, description="Optional candidate bus number")
    score: Optional[float] = Field(default=None, description="Optional suitability score")
    priority: Optional[str] = Field(default=None, description="Optional priority tier")


class ReallocationReviewResponse(BaseModel):
    """Schema representing a recorded dispatcher review decision."""

    id: int
    recommendation_id: str
    decision: str
    dispatcher_id: Optional[str] = None
    target_route_id: Optional[int] = None
    target_route_number: Optional[str] = None
    source_route_id: Optional[int] = None
    source_route_number: Optional[str] = None
    candidate_bus_id: Optional[int] = None
    candidate_bus_number: Optional[str] = None
    score: Optional[float] = None
    priority: Optional[str] = None
    notes: Optional[str] = None
    execution_status: Optional[str] = Field(
        default="NOT_EXECUTED",
        description="Execution status: NOT_EXECUTED, EXECUTED, or FAILED",
    )
    executed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    is_advisory: bool = Field(
        default=True,
        description="Approval confirms operational consideration only; execution requires explicit authorization.",
    )
    advisory_note: str = Field(
        default=(
            "Decision recorded for operational consideration only. Use explicit execution to dispatch vehicle."
        ),
        description="Explicit advisory disclaimer",
    )

    model_config = ConfigDict(from_attributes=True)


class ReallocationRecommendationResponse(BaseModel):
    """Structured rule-based fleet reallocation recommendation.

    Represents an advisory suggestion to reallocate a candidate bus from an
    underutilized source route to an overloaded target route to balance transit demand.
    """

    id: str = Field(
        ...,
        description="Unique deterministic recommendation identifier (e.g. REC-TARGET-SOURCE-BUS)",
    )

    # Source route attributes (providing spare capacity)
    source_route_id: int
    source_route_number: str
    source_route_name: Optional[str] = None
    source_route_load_factor: float
    source_route_status: str
    source_route: Optional[RouteBrief] = None

    # Target route attributes (demanding capacity assistance)
    target_route_id: int
    target_route_number: str
    target_route_name: Optional[str] = None
    target_route_load_factor: float
    target_route_status: str
    target_route: Optional[RouteBrief] = None

    # Candidate bus attributes (if identified)
    candidate_bus_id: Optional[int] = None
    candidate_bus_number: Optional[str] = None
    bus_capacity: Optional[int] = None
    current_occupancy: Optional[int] = None
    available_capacity: Optional[int] = None
    bus_load_factor: Optional[float] = None
    candidate_bus: Optional[BusBrief] = None

    # Geographic and transit proximity metrics (None when telemetry unavailable)
    distance_meters: Optional[float] = None
    estimated_travel_time_minutes: Optional[float] = None

    # Projected load impacts after potential reallocation
    projected_target_load_factor: Optional[float] = None
    projected_source_load_factor: Optional[float] = None

    # Evaluation, explanation and scoring
    score: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Deterministic suitability score from 0.0 to 100.0",
    )
    priority: str = Field(
        ...,
        description="Recommendation priority tier: HIGH, MEDIUM, or LOW",
    )
    feasibility_status: str = Field(
        ...,
        description="Operational feasibility: FEASIBLE, CONDITIONALLY_FEASIBLE, LIMITED_DATA, or INFEASIBLE",
    )
    limitations: List[str] = Field(
        default_factory=list,
        description="Operational constraints, data limitations, or pre-conditions",
    )
    reason: str = Field(
        ...,
        description="Human-readable explainable rationale for the recommendation",
    )

    # Advisory status guarantee
    is_advisory: bool = Field(
        default=True,
        description="Indicates that recommendation is advisory only; no automated route reassignment has occurred.",
    )
    advisory_note: str = Field(
        default=(
            "Advisory only. Rule-based recommendation requires transit controller review "
            "and authorization before dispatch. No automated reassignments have been made."
        ),
        description="Explicit advisory disclaimer",
    )

    # Stage 7 Dispatcher Review status
    review_status: Optional[str] = Field(
        default=None,
        description="Current dispatcher review decision (APPROVED, REJECTED, DEFERRED, or None)",
    )
    latest_review: Optional[ReallocationReviewResponse] = Field(
        default=None,
        description="Most recent dispatcher review details",
    )

    # Execution status
    execution_status: Optional[str] = Field(
        default=None,
        description="Execution status of this recommendation (NOT_EXECUTED, EXECUTED, FAILED, or None)",
    )
    executed_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp when recommendation was executed",
    )
    latest_execution: Optional[ReallocationExecutionResponse] = Field(
        default=None,
        description="Most recent execution record details",
    )

    model_config = ConfigDict(from_attributes=True)


class OptimizationOverviewResponse(BaseModel):
    """System-wide overview of optimization recommendations and reviews."""

    total_recommendations: int
    high_priority_count: int
    medium_priority_count: int
    low_priority_count: int
    feasible_count: int
    conditionally_feasible_count: int
    infeasible_count: int
    approved_count: int = Field(default=0, description="Count of approved recommendations")
    rejected_count: int = Field(default=0, description="Count of rejected recommendations")
    deferred_count: int = Field(default=0, description="Count of deferred recommendations")
    pending_count: int = Field(default=0, description="Count of pending recommendations")
    executed_count: int = Field(default=0, description="Count of executed recommendations")
    is_advisory: bool = True
    disclaimer: str = (
        "All optimization recommendations are strictly advisory. Final dispatch authority "
        "remains with human transit controllers."
    )
    diagnostic_reasons: List[str] = Field(
        default_factory=list,
        description="Diagnostic explanations when high-demand routes have no eligible donor buses",
    )

    model_config = ConfigDict(from_attributes=True)
