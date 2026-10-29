"""SQLAlchemy model for Bus Breakdown Incidents.

Phase 4: Manages bus mechanical breakdowns, emergency status transitions,
and recovery lifecycle (REPORTED -> CONFIRMED -> UNDER_REPAIR -> AVAILABLE).
"""
from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Integer, Float, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.bus import Bus
    from app.models.route import Route


class BusBreakdown(Base):
    """Tracks bus mechanical breakdowns, emergency status, and recovery lifecycle."""

    __tablename__ = "bus_breakdowns"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    bus_id: Mapped[int] = mapped_column(
        ForeignKey("buses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    bus_number: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    route_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("routes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    route_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Location coordinates at time of breakdown
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    location_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Breakdown lifecycle: REPORTED -> CONFIRMED -> UNDER_REPAIR -> AVAILABLE
    status: Mapped[str] = mapped_column(
        String(50), default="REPORTED", nullable=False, index=True
    )
    severity: Mapped[str] = mapped_column(String(50), default="HIGH", nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(
        String(50), default="LIVE", nullable=False
    )  # LIVE or SIMULATION

    reported_by: Mapped[str] = mapped_column(
        String(100), default="DISPATCHER-1", nullable=False
    )
    recovered_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    recovered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    bus: Mapped["Bus"] = relationship("Bus", foreign_keys=[bus_id])
    route: Mapped[Optional["Route"]] = relationship("Route", foreign_keys=[route_id])
