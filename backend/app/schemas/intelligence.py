"""Intelligence schemas for load analysis, fleet monitoring, and reallocation opportunity detection."""
from typing import Optional
from pydantic import BaseModel, ConfigDict


class IntelligenceOverviewResponse(BaseModel):
    """System-wide summary of fleet and route load status."""

    total_routes: int
    total_buses: int
    low_routes: int
    normal_routes: int
    high_routes: int
    critical_routes: int
    routes_needing_attention: int
    potential_reallocation_opportunities: int

    model_config = ConfigDict(from_attributes=True)


class RouteIntelligenceResponse(BaseModel):
    """Detailed load intelligence assessment for an individual transit route."""

    route_id: int
    route_number: str
    number_of_buses: int
    total_passengers: int
    total_capacity: int
    available_seats: int
    load_factor: float
    status: str
    assessment: str
    demand_profile: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class BusIntelligenceResponse(BaseModel):
    """Detailed load intelligence for an individual bus."""

    bus_id: int
    bus_number: str
    route_id: Optional[int] = None
    route_number: Optional[str] = None
    home_route_id: Optional[int] = None
    home_route_number: Optional[str] = None
    assigned_route_id: Optional[int] = None
    assigned_route_number: Optional[str] = None
    active_route_id: Optional[int] = None
    active_route_number: Optional[str] = None
    passenger_count: int
    capacity: int
    available_seats: int
    load_factor: float
    status: str
    is_transferring: bool = False
    transfer_status: Optional[str] = None
    target_route_id: Optional[int] = None
    target_route_number: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ReallocationOpportunityResponse(BaseModel):
    """Explainable opportunity pairing an overloaded route with an underutilized route."""

    overloaded_route_id: int
    overloaded_route_number: str
    overloaded_route_status: str
    overloaded_route_load_factor: float
    underutilized_route_id: int
    underutilized_route_number: str
    underutilized_route_load_factor: float
    reason: str

    model_config = ConfigDict(from_attributes=True)
