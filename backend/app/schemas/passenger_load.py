from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class PassengerLoadBase(BaseModel):
    bus_id: int
    stop_id: Optional[int] = None
    current_load: int
    capacity: int
    load_factor: float


class PassengerLoadCreate(PassengerLoadBase):
    timestamp: Optional[datetime] = None


class PassengerLoadRead(PassengerLoadBase):
    id: int
    timestamp: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
