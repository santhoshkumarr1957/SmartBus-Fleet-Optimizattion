from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class BusPositionBase(BaseModel):
    bus_id: int
    latitude: float
    longitude: float
    speed: float = 0.0
    heading: Optional[float] = None


class BusPositionCreate(BusPositionBase):
    timestamp: Optional[datetime] = None


class BusPositionRead(BusPositionBase):
    id: int
    timestamp: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
