from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class StopBase(BaseModel):
    route_id: int
    name: str
    stop_code: Optional[str] = None
    sequence_order: int
    latitude: float
    longitude: float


class StopCreate(StopBase):
    pass


class StopUpdate(BaseModel):
    route_id: Optional[int] = None
    name: Optional[str] = None
    stop_code: Optional[str] = None
    sequence_order: Optional[int] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class StopRead(StopBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
