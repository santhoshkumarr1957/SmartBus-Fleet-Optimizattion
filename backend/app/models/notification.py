"""SQLAlchemy model for Notifications and Alert Management (Stage 9).

Persists operational transit alerts (critical route loads, high loads,
bus breakdowns, route disruptions, and advisory reallocation opportunities)
and tracks dispatcher acknowledgement and resolution workflows.
"""
from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.route import Route
    from app.models.bus import Bus


class Notification(Base):
    """Notification and Alert record for transit operations (Stage 9)."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    alert_type: Mapped[str] = mapped_column(
        String(50),
        index=True,
        nullable=False,
        doc="CRITICAL_ROUTE_LOAD, HIGH_ROUTE_LOAD, BUS_BREAKDOWN, ROUTE_DISRUPTION, REALLOCATION_OPPORTUNITY, SIMULATION_NOTICE",
    )
    severity: Mapped[str] = mapped_column(
        String(20),
        index=True,
        nullable=False,
        doc="CRITICAL, HIGH, WARNING, INFO",
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(
        String(20),
        default="LIVE",
        index=True,
        nullable=False,
        doc="LIVE or SIMULATION",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="ACTIVE",
        index=True,
        nullable=False,
        doc="ACTIVE, ACKNOWLEDGED, RESOLVED",
    )
    dedup_key: Mapped[str] = mapped_column(
        String(150),
        index=True,
        nullable=False,
        doc="Deterministic composite key for deduplication and recurrence",
    )

    # Correlated entity references
    route_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("routes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    route_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    bus_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("buses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    bus_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Dispatcher review & resolution tracking
    acknowledged_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    route: Mapped[Optional["Route"]] = relationship("Route")
    bus: Mapped[Optional["Bus"]] = relationship("Bus")
