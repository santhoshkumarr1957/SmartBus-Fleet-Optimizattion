"""Live operational schemas for buses and routes."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class BusLiveResponse(BaseModel):
    """Schema representing the real-time operational status of an individual bus."""

    bus_id: int
    bus_number: str
    route_id: Optional[int] = None
    route_number: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    speed: Optional[float] = None
    heading: Optional[float] = None
    passenger_count: Optional[int] = None
    capacity: int
    load_factor: Optional[float] = None
    home_route_id: Optional[int] = None
    home_route_number: Optional[str] = None
    assigned_route_id: Optional[int] = None
    assigned_route_number: Optional[str] = None
    active_route_id: Optional[int] = None
    active_route_number: Optional[str] = None
    is_transferring: Optional[bool] = False
    transfer_status: Optional[str] = None
    target_route_id: Optional[int] = None
    target_route_number: Optional[str] = None
    direction: Optional[str] = None
    timestamp: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class RouteLiveResponse(BaseModel):
    """Schema representing live aggregate statistics for an individual transit route."""

    route_id: int
    route_number: str
    number_of_buses: int
    total_passengers: int
    total_capacity: int
    load_factor: float
    status: str
    demand_profile: Optional[str] = "NORMAL"

    model_config = ConfigDict(from_attributes=True)
