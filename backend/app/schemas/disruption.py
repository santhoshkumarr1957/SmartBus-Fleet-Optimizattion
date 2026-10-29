"""Pydantic schemas for Stage 8: Transit Disruption Simulation and Resilience Analysis.

Defines schemas for disruption types, simulation requests, before-and-after
impact comparisons, resilience metrics, and isolated scenario responses.
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.optimization import ReallocationRecommendationResponse


class DisruptionTypeInfo(BaseModel):
    """Metadata describing a supported disruption scenario type."""

    type: str = Field(..., description="Unique scenario type identifier (e.g. BUS_BREAKDOWN)")
    name: str = Field(..., description="Human-readable title")
    description: str = Field(..., description="Explanation of simulated real-world conditions")
    required_parameters: List[str] = Field(default_factory=list)
    optional_parameters: List[str] = Field(default_factory=list)
    example_parameters: Dict[str, Any] = Field(default_factory=dict)


class DisruptionSimulationRequest(BaseModel):
    """Request payload to execute a rule-based transit disruption simulation."""

    disruption_type: str = Field(
        ...,
        description="Type of disruption: BUS_BREAKDOWN, ROUTE_CLOSURE, DEMAND_SPIKE, or SERVICE_DELAY",
        examples=["BUS_BREAKDOWN", "ROUTE_CLOSURE", "DEMAND_SPIKE", "SERVICE_DELAY"],
    )
    bus_id: Optional[int] = Field(
        default=None,
        description="Target bus ID for breakdown or vehicle-specific delay",
    )
    bus_number: Optional[str] = Field(
        default=None,
        description="Target bus number (e.g. '101A')",
    )
    route_id: Optional[int] = Field(
        default=None,
        description="Target route ID for closure, demand spike, or route-wide delay",
    )
    route_number: Optional[str] = Field(
        default=None,
        description="Target route number (e.g. '101')",
    )
    spike_percentage: Optional[float] = Field(
        default=None,
        ge=5.0,
        le=300.0,
        description="Passenger demand increase percentage for DEMAND_SPIKE/DEMAND_SURGE (e.g. 50.0 for +50%)",
    )
    demand_multiplier: Optional[float] = Field(
        default=None,
        ge=1.05,
        le=4.0,
        description="Demand multiplier factor for DEMAND_SPIKE/DEMAND_SURGE (e.g. 1.5 for +50% surge)",
    )
    demand_percentage: Optional[float] = Field(
        default=None,
        ge=5.0,
        le=300.0,
        description="Alternative percentage alias for spike_percentage",
    )
    delay_minutes: Optional[float] = Field(
        default=None,
        ge=1.0,
        le=240.0,
        description="Service delay duration in minutes for SERVICE_DELAY (e.g. 20.0)",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Operator remarks or scenario justification",
    )


class RouteImpactSummary(BaseModel):
    """Comparative before-and-after assessment for an individual transit route."""

    route_id: int
    route_number: str
    name: Optional[str] = None
    status_before: str
    status_after: str
    load_factor_before: float
    load_factor_after: float
    passengers_before: int
    passengers_after: int
    capacity_before: int
    capacity_after: int
    available_seats_before: int
    available_seats_after: int
    buses_count_before: int
    buses_count_after: int
    is_directly_affected: bool
    severity_change: str = Field(
        ...,
        description="UNCHANGED, DEGRADED, SEVERELY_DEGRADED, or CLOSED",
    )
    assessment: str

    model_config = ConfigDict(from_attributes=True)


class BusImpactSummary(BaseModel):
    """Comparative before-and-after status for an individual transit bus."""

    bus_id: int
    bus_number: str
    route_id: Optional[int] = None
    route_number: Optional[str] = None
    status_before: str
    status_after: str
    is_operational_after: bool
    passenger_count_before: int
    passenger_count_after: int
    capacity: int
    load_factor_before: float
    load_factor_after: float
    impact_note: str

    model_config = ConfigDict(from_attributes=True)


class ResilienceMetrics(BaseModel):
    """Deterministic, transparent network resilience metrics for a scenario."""

    fleet_availability_pct: float = Field(
        ...,
        description="Percentage of fleet vehicles remaining active in service (0.0 to 100.0%)",
    )
    capacity_retention_pct: float = Field(
        ...,
        description="Percentage of baseline seat capacity retained after disruption (0.0 to 100.0%)",
    )
    capacity_lost: int = Field(
        ...,
        description="Absolute physical passenger seat capacity lost due to disruption",
    )
    capacity_loss_pct: float = Field(
        ...,
        description="Percentage of total baseline capacity lost (0.0 to 100.0%)",
    )
    service_continuity_pct: float = Field(
        ...,
        description="Percentage of transit routes remaining operational (0.0 to 100.0%)",
    )
    routes_affected_count: int = Field(
        ...,
        description="Number of routes directly impacted or experiencing load degradation",
    )
    routes_critical_count: int = Field(
        ...,
        description="Number of routes reaching CRITICAL status (load factor >= 1.00) in scenario",
    )
    routes_high_count: int = Field(
        ...,
        description="Number of routes reaching HIGH status (0.80 <= load factor < 1.00) in scenario",
    )
    remaining_available_capacity: int = Field(
        ...,
        description="Total remaining surplus seats across all operational corridors",
    )
    resilience_score: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Composite rule-based resilience rating from 0.0 (catastrophic) to 100.0 (fully resilient)",
    )
    resilience_rating: str = Field(
        ...,
        description="Qualitative tier: EXCELLENT, ADEQUATE, VULNERABLE, or CRITICAL",
    )


class DisruptionSimulationResponse(BaseModel):
    """Complete impact analysis and resilience assessment for a disruption scenario."""

    scenario_id: str = Field(
        ...,
        description="Unique deterministic identifier for the simulated scenario",
    )
    disruption_type: str = Field(
        ...,
        description="Simulated scenario type (BUS_BREAKDOWN, ROUTE_CLOSURE, etc.)",
    )
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Resolved parameters used to generate the scenario",
    )
    simulated_at: datetime = Field(
        ...,
        description="UTC timestamp of simulation execution",
    )

    # Executive Summary
    summary_headline: str
    executive_summary: str

    # Global Resilience Metrics
    resilience_metrics: ResilienceMetrics

    # Detailed Entities
    affected_routes: List[RouteImpactSummary]
    affected_buses: List[BusImpactSummary]

    # Reallocation options based on simulated congestion
    suggested_reallocations: List[ReallocationRecommendationResponse] = Field(
        default_factory=list,
        description="Advisory reallocation opportunities that could mitigate simulated congestion",
    )

    # Operational warnings triggered by disruption
    warnings: List[str] = Field(
        default_factory=list,
        description="Operational warnings and alerts triggered by the simulated disruption",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Operator remarks or scenario justification",
    )

    # Strict isolation guarantee
    is_simulated: bool = Field(
        default=True,
        description="Guarantees this is a simulated calculation without modifying live database records",
    )
    disclaimer: str = Field(
        default=(
            "SIMULATED DATA — NO LIVE CHANGES. Calculated in-memory on scenario snapshot; "
            "live telemetry, bus assignments, and review records remain completely unaltered."
        ),
        description="Explicit scenario isolation disclaimer",
    )

    model_config = ConfigDict(from_attributes=True)


class DisruptionScenarioBrief(BaseModel):
    """Concise representation of a previously simulated scenario in the active cache."""

    scenario_id: str
    disruption_type: str
    target_description: str
    simulated_at: datetime
    resilience_score: float
    resilience_rating: str
    routes_affected_count: int
    capacity_lost: int

    model_config = ConfigDict(from_attributes=True)
