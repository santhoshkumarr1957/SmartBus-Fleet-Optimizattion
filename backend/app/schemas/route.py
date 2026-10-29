from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class RouteBase(BaseModel):
    route_number: str
    name: str
    description: Optional[str] = None
    origin: str
    destination: str
    is_active: bool = True


class RouteCreate(RouteBase):
    pass


class RouteUpdate(BaseModel):
    route_number: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    origin: Optional[str] = None
    destination: Optional[str] = None
    is_active: Optional[bool] = None


class RouteRead(RouteBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


from app.schemas.stop import StopRead
from typing import List


class RouteDetailedRead(RouteRead):
    stops: List[StopRead] = []

    model_config = ConfigDict(from_attributes=True)
