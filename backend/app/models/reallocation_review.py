"""SQLAlchemy model for Dispatcher Reallocation Reviews (Stage 7).

Persists human transit dispatcher decisions (APPROVED, REJECTED, DEFERRED)
for Stage 5 rule-based fleet reallocation recommendations without altering
bus route assignments or executing automatic dispatches.
"""
from datetime import datetime
from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import String, Integer, Float, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.route import Route
    from app.models.bus import Bus
    from app.models.reallocation_execution import ReallocationExecution


class ReallocationReview(Base):
    """Dispatcher review decision for a fleet reallocation recommendation.

    Represents a formal dispatcher determination regarding whether an advisory
    reallocation recommendation is approved for operational consideration,
    rejected due to local constraints, or deferred for re-evaluation.
    """

    __tablename__ = "reallocation_reviews"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    recommendation_id: Mapped[str] = mapped_column(
        String(100), index=True, nullable=False, doc="Unique recommendation identifier"
    )
    decision: Mapped[str] = mapped_column(
        String(50), index=True, nullable=False, doc="APPROVED, REJECTED, or DEFERRED"
    )
    dispatcher_id: Mapped[Optional[str]] = mapped_column(
        String(100), default="DISPATCHER-1", nullable=True, doc="Reviewing dispatcher username or ID"
    )

    # Context snapshot attributes
    target_route_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("routes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    target_route_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    source_route_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("routes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_route_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    candidate_bus_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("buses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    candidate_bus_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    priority: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Dispatcher rationale / operational comments
    notes: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, doc="Dispatcher remarks, field conditions, or operational reasoning"
    )

    # Execution tracking attributes
    execution_status: Mapped[Optional[str]] = mapped_column(
        String(50), default="NOT_EXECUTED", nullable=True, doc="NOT_EXECUTED, EXECUTED, or FAILED"
    )
    executed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, doc="Timestamp when execution occurred"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Optional relationships
    target_route: Mapped[Optional["Route"]] = relationship(
        "Route", foreign_keys=[target_route_id]
    )
    source_route: Mapped[Optional["Route"]] = relationship(
        "Route", foreign_keys=[source_route_id]
    )
    candidate_bus: Mapped[Optional["Bus"]] = relationship(
        "Bus", foreign_keys=[candidate_bus_id]
    )
    executions: Mapped[List["ReallocationExecution"]] = relationship(
        "ReallocationExecution", back_populates="review"
    )
