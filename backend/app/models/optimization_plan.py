"""SQLAlchemy model for Hybrid Optimization Plans.

Phases 1, 2, 6, 8: Persists generated mathematical optimization plans,
solver status, before/after impact predictions, weather factors, and allocations.
"""
from datetime import datetime
from typing import Optional, Any
from sqlalchemy import String, Integer, Float, Text, DateTime, JSON, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class OptimizationPlan(Base):
    """Persists generated hybrid optimization plans and before/after evaluation summaries."""

    __tablename__ = "optimization_plans"

    id: Mapped[str] = mapped_column(String(100), primary_key=True, index=True)
    status: Mapped[str] = mapped_column(
        String(50), default="GENERATED", nullable=False, index=True
    )  # GENERATED, APPROVED, EXECUTED, SUPERSEDED, REJECTED
    solver_status: Mapped[str] = mapped_column(
        String(50), default="OPTIMAL", nullable=False
    )  # OPTIMAL, FEASIBLE, INFEASIBLE, NO_IMBALANCE

    objective_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    solver_time_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Weather snapshot at plan generation time
    weather_condition: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    weather_delay_factor: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Network before & after indicators
    baseline_overloaded_routes: Mapped[int] = mapped_column(Integer, default=0)
    predicted_overloaded_routes: Mapped[int] = mapped_column(Integer, default=0)
    baseline_unmet_demand: Mapped[int] = mapped_column(Integer, default=0)
    predicted_unmet_demand: Mapped[int] = mapped_column(Integer, default=0)
    total_transfer_distance_km: Mapped[float] = mapped_column(Float, default=0.0)
    total_transfer_time_min: Mapped[float] = mapped_column(Float, default=0.0)

    # Allocations and Diagnostic JSON
    allocations_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    binding_constraints_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    summary_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
