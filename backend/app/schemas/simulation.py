"""Schemas for Transit Traffic Simulation control and monitoring."""
from typing import Optional, List, Dict
from pydantic import BaseModel, Field


class RouteDemandItem(BaseModel):
    """Demand profile status for a single route."""

    route_id: int = Field(..., description="Route database ID")
    route_number: str = Field(..., description="Route display number, e.g. '101'")
    route_name: Optional[str] = Field(None, description="Corridor name")
    demand_profile: str = Field(..., description="Active demand profile: LOW, NORMAL, or HIGH")


class RouteDemandUpdateRequest(BaseModel):
    """Payload to update demand profile for a specific route."""

    profile: str = Field(
        ...,
        description="Target demand profile: 'LOW', 'NORMAL', or 'HIGH'",
        example="HIGH",
    )


class RouteDemandResponse(BaseModel):
    """Response after updating or fetching route demand profile."""

    route_id: int = Field(..., description="Route database ID")
    route_number: str = Field(..., description="Route display number, e.g. '101'")
    route_name: Optional[str] = Field(None, description="Corridor name")
    demand_profile: str = Field(..., description="Active demand profile: LOW, NORMAL, or HIGH")
    message: str = Field(..., description="Status message")


class SimulationStatusResponse(BaseModel):
    """Real-time status report of the transit fleet simulation engine."""

    status: str = Field(..., description="Current engine state: RUNNING, PAUSED, or STOPPED")
    active_profile: str = Field(..., description="Active demand profile: LOW, NORMAL, or HIGH")
    scenario: str = Field(..., description="Internal scenario identifier")
    speed: int = Field(default=1, description="Speed multiplier: 1, 2, or 5")
    interval_seconds: float = Field(..., description="Base simulation interval in seconds")
    effective_interval: float = Field(..., description="Effective tick interval considering speed")
    is_running: bool = Field(..., description="Whether simulation thread is active")
    is_paused: bool = Field(..., description="Whether simulation progression is temporarily paused")
    tick_count: int = Field(default=0, description="Total simulation ticks executed")
    started_at: Optional[str] = Field(None, description="ISO timestamp when simulation was started")
    elapsed_seconds: int = Field(default=0, description="Total elapsed seconds since started")
    last_updated: Optional[str] = Field(None, description="ISO timestamp of last simulation tick")
    total_buses: int = Field(default=12, description="Total buses simulated")
    total_routes: int = Field(default=6, description="Total active transit routes")
    route_demands: Dict[str, str] = Field(
        default_factory=dict,
        description="Active demand profile by route number (e.g. {'101': 'HIGH', '202': 'LOW'})",
    )
    route_demand_list: Optional[List[RouteDemandItem]] = Field(
        default=None,
        description="Detailed list of route demand configurations",
    )
    message: str = Field(..., description="Descriptive status message")


class SimulationProfileInfo(BaseModel):
    """Information regarding a supported demand profile."""

    id: str = Field(..., description="Profile code: LOW, NORMAL, or HIGH")
    name: str = Field(..., description="Human-readable profile name")
    description: str = Field(..., description="Detailed profile explanation")
    is_active: bool = Field(default=False, description="Whether this profile is currently active")
    tag: Optional[str] = Field(None, description="Category or badge tag")


class SimulationDemandRequest(BaseModel):
    """Payload to switch active demand profile."""

    profile: str = Field(
        ...,
        description="Target demand profile: 'LOW', 'NORMAL', or 'HIGH'",
        example="HIGH",
    )


class SimulationSpeedRequest(BaseModel):
    """Payload to adjust simulation speed multiplier."""

    speed: int = Field(
        ...,
        description="Speed multiplier: 1, 2, or 5",
        example=2,
    )


class SimulationEventItem(BaseModel):
    """Log entry for significant simulation events."""

    id: str = Field(..., description="Unique event identifier")
    timestamp: str = Field(..., description="ISO UTC timestamp of the event")
    type: str = Field(..., description="Event category: LIFECYCLE, DEMAND_CHANGE, SPEED_CHANGE, ROUTE_LOAD, RESET")
    level: str = Field(..., description="Severity level: info, warning, critical, success")
    message: str = Field(..., description="Human-readable event description")


class SimulationKpiResponse(BaseModel):
    """Aggregated live KPIs for the traffic simulation dashboard."""

    total_active_buses: int = Field(..., description="Count of currently active buses")
    total_routes: int = Field(..., description="Count of operational transit routes")
    average_load_factor: float = Field(..., description="System-wide average passenger load factor")
    low_load_routes_count: int = Field(..., description="Count of routes with LOW load factor (<50%)")
    normal_load_routes_count: int = Field(..., description="Count of routes with NORMAL load factor (50-80%)")
    high_load_routes_count: int = Field(..., description="Count of routes with HIGH load factor (80-100%)")
    critical_load_routes_count: int = Field(..., description="Count of routes with CRITICAL load factor (>=100%)")
    attention_required_count: int = Field(..., description="Count of routes requiring operational attention")
    total_fleet_capacity: int = Field(..., description="Sum of passenger capacities across all active buses")
    total_passengers: int = Field(..., description="Current total passengers aboard active fleet")
    available_capacity_seats: int = Field(..., description="Remaining unoccupied passenger seats in fleet")
    active_profile: str = Field(..., description="Active demand profile: LOW, NORMAL, or HIGH")
    simulation_status: str = Field(..., description="Simulation engine state: RUNNING, PAUSED, or STOPPED")
