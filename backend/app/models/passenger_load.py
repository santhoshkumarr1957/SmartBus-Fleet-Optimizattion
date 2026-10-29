from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import Integer, Float, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.bus import Bus
    from app.models.stop import Stop


class PassengerLoad(Base):
    __tablename__ = "passenger_loads"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    bus_id: Mapped[int] = mapped_column(ForeignKey("buses.id", ondelete="CASCADE"), nullable=False, index=True)
    stop_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("stops.id", ondelete="SET NULL"), nullable=True, index=True
    )
    current_load: Mapped[int] = mapped_column(Integer, nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    load_factor: Mapped[float] = mapped_column(Float, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    bus: Mapped["Bus"] = relationship("Bus", back_populates="passenger_loads")
    stop: Mapped[Optional["Stop"]] = relationship("Stop", back_populates="passenger_loads")
