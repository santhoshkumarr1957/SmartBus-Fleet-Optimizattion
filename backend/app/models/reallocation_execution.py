"""SQLAlchemy model for Reallocation Executions.

Persists the formal execution and runtime dispatch of an approved bus route reallocation,
recording source and target routes, candidate bus, executing dispatcher, status,
and operational audit details.
"""
from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.route import Route
    from app.models.bus import Bus
    from app.models.reallocation_review import ReallocationReview


class ReallocationExecution(Base):
    """Execution record for an authorized fleet reallocation recommendation."""

    __tablename__ = "reallocation_executions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    recommendation_id: Mapped[str] = mapped_column(
        String(100), index=True, nullable=False, doc="Unique recommendation identifier"
    )
    review_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("reallocation_reviews.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="Referenced approved review decision ID",
    )
    bus_id: Mapped[int] = mapped_column(
        ForeignKey("buses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    bus_number: Mapped[str] = mapped_column(String(50), nullable=False)
    source_route_id: Mapped[int] = mapped_column(
        ForeignKey("routes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_route_number: Mapped[str] = mapped_column(String(50), nullable=False)
    target_route_id: Mapped[int] = mapped_column(
        ForeignKey("routes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_route_number: Mapped[str] = mapped_column(String(50), nullable=False)
    dispatcher_id: Mapped[str] = mapped_column(
        String(100), default="DISPATCHER-1", nullable=False, doc="Reviewing dispatcher username or ID"
    )
    status: Mapped[str] = mapped_column(
        String(50), index=True, nullable=False, doc="EXECUTED, IN_PROGRESS, or FAILED"
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, doc="Error message explaining failure if status is FAILED"
    )
    notes: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, doc="Operational comments or instructions"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    review: Mapped[Optional["ReallocationReview"]] = relationship(
        "ReallocationReview", back_populates="executions"
    )
    bus: Mapped["Bus"] = relationship("Bus", foreign_keys=[bus_id])
    source_route: Mapped["Route"] = relationship("Route", foreign_keys=[source_route_id])
    target_route: Mapped["Route"] = relationship("Route", foreign_keys=[target_route_id])
