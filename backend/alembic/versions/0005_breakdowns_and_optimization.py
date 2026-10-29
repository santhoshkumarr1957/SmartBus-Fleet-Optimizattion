"""Migration 0005: Bus Breakdowns and Optimization Plans

Creates the bus_breakdowns and optimization_plans tables for tracking
vehicle breakdown lifecycles, emergency recovery, and hybrid CP-SAT optimization plans.

Revision ID: 0005_breakdowns_optimization
Revises: 0004_executions
Create Date: 2026-10-28
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0005_breakdowns_optimization"
down_revision: Union[str, None] = "0004_executions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create bus_breakdowns table
    op.create_table(
        "bus_breakdowns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bus_id", sa.Integer(), nullable=False),
        sa.Column("bus_number", sa.String(length=50), nullable=False),
        sa.Column("route_id", sa.Integer(), nullable=True),
        sa.Column("route_number", sa.String(length=50), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("location_name", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=50), server_default="REPORTED", nullable=False),
        sa.Column("severity", sa.String(length=50), server_default="HIGH", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=50), server_default="LIVE", nullable=False),
        sa.Column("reported_by", sa.String(length=100), server_default="DISPATCHER-1", nullable=False),
        sa.Column("recovered_by", sa.String(length=100), nullable=True),
        sa.Column(
            "reported_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("recovered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["bus_id"], ["buses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["route_id"], ["routes.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_bus_breakdowns_id"),
        "bus_breakdowns",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_bus_breakdowns_bus_id"),
        "bus_breakdowns",
        ["bus_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_bus_breakdowns_bus_number"),
        "bus_breakdowns",
        ["bus_number"],
        unique=False,
    )
    op.create_index(
        op.f("ix_bus_breakdowns_route_id"),
        "bus_breakdowns",
        ["route_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_bus_breakdowns_status"),
        "bus_breakdowns",
        ["status"],
        unique=False,
    )

    # 2. Create optimization_plans table
    op.create_table(
        "optimization_plans",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=50), server_default="GENERATED", nullable=False),
        sa.Column("solver_status", sa.String(length=50), server_default="OPTIMAL", nullable=False),
        sa.Column("objective_value", sa.Float(), nullable=True),
        sa.Column("solver_time_ms", sa.Float(), nullable=True),
        sa.Column("weather_condition", sa.String(length=50), nullable=True),
        sa.Column("weather_delay_factor", sa.Float(), nullable=True),
        sa.Column("baseline_overloaded_routes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("predicted_overloaded_routes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("baseline_unmet_demand", sa.Integer(), server_default="0", nullable=False),
        sa.Column("predicted_unmet_demand", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_transfer_distance_km", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("total_transfer_time_min", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("allocations_json", sa.JSON(), nullable=True),
        sa.Column("binding_constraints_json", sa.JSON(), nullable=True),
        sa.Column("summary_notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_optimization_plans_id"),
        "optimization_plans",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_optimization_plans_status"),
        "optimization_plans",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_optimization_plans_status"), table_name="optimization_plans")
    op.drop_index(op.f("ix_optimization_plans_id"), table_name="optimization_plans")
    op.drop_table("optimization_plans")

    op.drop_index(op.f("ix_bus_breakdowns_status"), table_name="bus_breakdowns")
    op.drop_index(op.f("ix_bus_breakdowns_route_id"), table_name="bus_breakdowns")
    op.drop_index(op.f("ix_bus_breakdowns_bus_number"), table_name="bus_breakdowns")
    op.drop_index(op.f("ix_bus_breakdowns_bus_id"), table_name="bus_breakdowns")
    op.drop_index(op.f("ix_bus_breakdowns_id"), table_name="bus_breakdowns")
    op.drop_table("bus_breakdowns")
