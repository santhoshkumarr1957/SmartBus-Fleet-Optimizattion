from datetime import datetime
from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import String, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.route import Route
    from app.models.bus_position import BusPosition
    from app.models.passenger_load import PassengerLoad


class Bus(Base):
    __tablename__ = "buses"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    bus_number: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    license_plate: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    current_route_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("routes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(50), default="IDLE", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    current_route: Mapped[Optional["Route"]] = relationship("Route", back_populates="buses")
    positions: Mapped[List["BusPosition"]] = relationship(
        "BusPosition", back_populates="bus", cascade="all, delete-orphan"
    )
    passenger_loads: Mapped[List["PassengerLoad"]] = relationship(
        "PassengerLoad", back_populates="bus", cascade="all, delete-orphan"
    )
