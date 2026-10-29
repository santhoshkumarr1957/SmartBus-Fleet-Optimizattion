"""Pydantic schemas for TRANSIGHT Stage 10: Reports & Performance Analytics."""
from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


# -----------------------------------------------------------------------------
# A. Fleet Utilization Schemas
# -----------------------------------------------------------------------------

class BusUtilizationBrief(BaseModel):
    """Snapshot brief of individual bus utilization."""
    bus_id: int
    bus_number: str
    license_plate: str
    status: str
    capacity: int
    current_load: int
    available_seats: int
    load_factor: float
    current_route_id: Optional[int] = None
    current_route_number: Optional[str] = None

    class Config:
        from_attributes = True


class FleetUtilizationReportResponse(BaseModel):
    """Aggregate fleet capacity and vehicle utilization report."""
    generated_at: datetime
    time_scope: str = Field(
        default="CURRENT_OPERATIONAL_SNAPSHOT",
        description="Indicates whether values represent current snapshot or historical aggregates",
    )
    total_buses: int
    operational_buses: int
    inactive_buses: int
    broken_down_buses: int
    maintenance_buses: int
    fleet_availability_pct: float
    total_passenger_capacity: int
    total_current_passengers: int
    available_seats: int
    fleet_load_factor: float
    load_distribution: Dict[str, int] = Field(
        description="Counts of buses grouped by load factor: LOW (<50%), NORMAL (50-79%), HIGH (80-99%), CRITICAL (>=100%)"
    )
    buses: List[BusUtilizationBrief] = Field(default_factory=list)


# -----------------------------------------------------------------------------
# B. Route Performance Schemas
# -----------------------------------------------------------------------------

class RoutePerformanceItem(BaseModel):
    """Performance evaluation item for a specific transit route."""
    route_id: int
    route_number: str
    name: Optional[str] = None
    origin: Optional[str] = None
    destination: Optional[str] = None
    is_active: bool
    assigned_bus_count: int
    total_capacity: int
    total_passengers: int
    available_seats: int
    load_factor: float
    status: str = Field(description="LOW, NORMAL, HIGH, or CRITICAL")
    overcrowding_level: str

    class Config:
        from_attributes = True


class RoutePerformanceReportResponse(BaseModel):
    """Route comparison and network performance metrics."""
    generated_at: datetime
    time_scope: str = Field(
        default="CURRENT_OPERATIONAL_SNAPSHOT",
        description="Indicates whether values represent current snapshot or historical aggregates",
    )
    total_routes: int
    active_routes: int
    inactive_routes: int
    overloaded_routes_count: int = Field(
        description="Count of active routes with HIGH or CRITICAL load factor (>=80%)"
    )
    underutilized_routes_count: int = Field(
        description="Count of active routes with LOW load factor (<50%)"
    )
    highest_load_route: Optional[str] = None
    lowest_load_route: Optional[str] = None
    routes: List[RoutePerformanceItem] = Field(default_factory=list)


# -----------------------------------------------------------------------------
# C. Disruption Analysis Schemas
# -----------------------------------------------------------------------------

class DisruptionEventBrief(BaseModel):
    """Record of an operational alert or simulated scenario incident."""
    alert_id: int
    alert_type: str
    severity: str
    title: str
    description: str
    source: str = Field(description="'LIVE' for real incidents, 'SIMULATION' for simulated scenarios")
    status: str = Field(description="'ACTIVE', 'ACKNOWLEDGED', or 'RESOLVED'")
    route_number: Optional[str] = None
    bus_number: Optional[str] = None
    created_at: datetime
    resolved_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    resolved_by: Optional[str] = None

    class Config:
        from_attributes = True


class DisruptionReportResponse(BaseModel):
    """Audit analysis of operational disruption alerts and simulation scenarios."""
    generated_at: datetime
    live_incidents_total: int
    live_active_count: int
    live_acknowledged_count: int
    live_resolved_count: int
    live_breakdowns_count: int
    live_route_disruptions_count: int
    live_overcrowding_alerts_count: int
    live_events: List[DisruptionEventBrief] = Field(default_factory=list)
    simulation_scenarios_count: int
    simulated_events: List[DisruptionEventBrief] = Field(default_factory=list)
    is_simulation_isolated: bool = True
    disclaimer: str = Field(
        default="Live operational alerts and simulated scenarios are strictly isolated. Simulated results do not reflect real-world vehicle breakdowns or transit closures."
    )


# -----------------------------------------------------------------------------
# D. Reallocation & Dispatcher Review Schemas
# -----------------------------------------------------------------------------

class ReviewOutcomeBrief(BaseModel):
    """Historical record of dispatcher decision."""
    id: int
    recommendation_id: str
    decision: str
    dispatcher_id: Optional[str] = None
    target_route_number: Optional[str] = None
    source_route_number: Optional[str] = None
    candidate_bus_number: Optional[str] = None
    created_at: datetime
    notes: Optional[str] = None

    class Config:
        from_attributes = True


class ReallocationReportResponse(BaseModel):
    """Review audit and advisory reallocation metrics."""
    generated_at: datetime
    active_proposals_count: int
    high_priority_count: int
    medium_priority_count: int
    low_priority_count: int
    total_reviews_recorded: int
    approved_count: int
    rejected_count: int
    deferred_count: int
    pending_count: int
    recent_reviews: List[ReviewOutcomeBrief] = Field(default_factory=list)
    operational_limitation_statement: str = Field(
        default="The current database schema records dispatcher review decisions and advisory recommendations for supervisory oversight. In accordance with system safety constraints, APPROVED reviews do not execute automatic physical vehicle reassignments or track actual completed bus transfers."
    )


# -----------------------------------------------------------------------------
# E. Historical Trends Schemas
# -----------------------------------------------------------------------------

class TrendDataPoint(BaseModel):
    """Aggregated load factor and passenger metric for a single time bucket."""
    timestamp: str
    average_load_factor: float
    total_passengers: int
    peak_load_factor: float
    sample_count: int


class TrendsReportResponse(BaseModel):
    """Timeseries trends over configurable historical time windows."""
    generated_at: datetime
    time_range: str = Field(description="Configured range: '1h', '24h', or '7d'")
    bucket_interval: str = Field(description="Aggregation bucket interval: '5m', '1h', or '6h'")
    start_time: datetime
    end_time: datetime
    total_samples: int
    overall_average_load_factor: float
    peak_observed_load_factor: float
    datapoints: List[TrendDataPoint] = Field(default_factory=list)
    data_density_note: str


# -----------------------------------------------------------------------------
# F. Executive Reports Overview
# -----------------------------------------------------------------------------

class ReportsOverviewResponse(BaseModel):
    """Executive summary linking high-level performance indicators."""
    generated_at: datetime
    fleet: FleetUtilizationReportResponse
    routes: RoutePerformanceReportResponse
    disruptions_summary: Dict[str, int]
    reviews_summary: Dict[str, int]
    trends_preview: TrendsReportResponse
