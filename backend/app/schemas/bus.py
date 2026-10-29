from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class BusBase(BaseModel):
    bus_number: str
    license_plate: str
    capacity: int = 60
    current_route_id: Optional[int] = None
    status: str = "IDLE"


class BusCreate(BusBase):
    pass


class BusUpdate(BaseModel):
    bus_number: Optional[str] = None
    license_plate: Optional[str] = None
    capacity: Optional[int] = None
    current_route_id: Optional[int] = None
    status: Optional[str] = None


class BusRead(BusBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
