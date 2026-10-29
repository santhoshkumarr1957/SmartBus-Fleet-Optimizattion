"""Schemas for Bus Breakdown Management (Phase 4)."""
from datetime import datetime
from typing import List, Optional, Any
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.optimization import BusBrief, RouteBrief


class BreakdownReportRequest(BaseModel):
    """Dispatcher request to report a vehicle breakdown incident."""

    bus_id: Optional[int] = Field(default=None, description="Database ID of the broken bus")
    bus_number: Optional[str] = Field(default=None, description="Bus number (e.g. '101A')")
    route_id: Optional[int] = Field(default=None, description="Current assigned route ID")
    route_number: Optional[str] = Field(default=None, description="Current assigned route number")
    latitude: Optional[float] = Field(default=None, description="Last known latitude coordinate")
    longitude: Optional[float] = Field(default=None, description="Last known longitude coordinate")
    location_name: Optional[str] = Field(default=None, description="Descriptive location or stop name")
    status: Optional[str] = Field(default="REPORTED", description="REPORTED or CONFIRMED")
    severity: Optional[str] = Field(default="HIGH", description="Incident severity: MEDIUM, HIGH, CRITICAL")
    notes: Optional[str] = Field(default=None, description="Mechanical fault description or driver notes")
    source: Optional[str] = Field(default="LIVE", description="LIVE or SIMULATION")
    dispatcher_id: Optional[str] = Field(default="DISPATCHER-1", description="Reporting dispatcher ID")


class BreakdownStatusUpdateRequest(BaseModel):
    """Dispatcher request to advance the lifecycle of a breakdown incident."""

    status: str = Field(
        ...,
        description="Target status: CONFIRMED, UNDER_REPAIR, or AVAILABLE",
        examples=["CONFIRMED", "UNDER_REPAIR", "AVAILABLE"],
    )
    notes: Optional[str] = Field(default=None, description="Status update remarks or repair notes")
    dispatcher_id: Optional[str] = Field(default="DISPATCHER-1", description="Dispatcher ID")


class BreakdownResponse(BaseModel):
    """Detailed record of a bus breakdown incident."""

    id: int
    bus_id: int
    bus_number: str
    route_id: Optional[int] = None
    route_number: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_name: Optional[str] = None
    status: str
    severity: str
    notes: Optional[str] = None
    source: str
    reported_by: str
    recovered_by: Optional[str] = None
    reported_at: datetime
    recovered_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BreakdownSummaryResponse(BaseModel):
    """Consolidated summary of fleet breakdowns and availability impacts."""

    total_breakdowns: int
    active_breakdowns: int
    under_repair_count: int
    recovered_count: int
    affected_routes: List[str]
    fleet_availability_pct: float
    total_capacity_lost: int
    incidents: List[BreakdownResponse]


class ReplacementCandidateResponse(BaseModel):
    """Actionable candidate evaluation for replacing a broken-down vehicle."""

    broken_bus_id: int
    broken_bus_number: str
    route_id: Optional[int]
    route_number: Optional[str]
    capacity_lost: int
    candidate_donor_buses: List[BusBrief]
    eligible_donor_routes: List[RouteBrief]
    recommended_bus_id: Optional[int] = None
    recommended_bus_number: Optional[str] = None
    recommended_source_route: Optional[str] = None
    binding_constraints: List[str]
    explanation: str
