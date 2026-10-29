"""Initial SmartBus Schema: routes, buses, stops, bus_positions, passenger_loads

Revision ID: 0001_initial
Revises: 
Create Date: 2026-10-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Routes
    op.create_table(
        "routes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("route_number", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("origin", sa.String(length=255), nullable=False),
        sa.Column("destination", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("route_number"),
    )
    op.create_index(op.f("ix_routes_id"), "routes", ["id"], unique=False)
    op.create_index(op.f("ix_routes_route_number"), "routes", ["route_number"], unique=True)

    # 2. Buses
    op.create_table(
        "buses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bus_number", sa.String(length=50), nullable=False),
        sa.Column("license_plate", sa.String(length=50), nullable=False),
        sa.Column("capacity", sa.Integer(), server_default=sa.text("60"), nullable=False),
        sa.Column("current_route_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=50), server_default=sa.text("'IDLE'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["current_route_id"], ["routes.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bus_number"),
        sa.UniqueConstraint("license_plate"),
    )
    op.create_index(op.f("ix_buses_id"), "buses", ["id"], unique=False)
    op.create_index(op.f("ix_buses_bus_number"), "buses", ["bus_number"], unique=True)
    op.create_index(op.f("ix_buses_current_route_id"), "buses", ["current_route_id"], unique=False)

    # 3. Stops
    op.create_table(
        "stops",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("route_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("stop_code", sa.String(length=50), nullable=True),
        sa.Column("sequence_order", sa.Integer(), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["route_id"], ["routes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_stops_id"), "stops", ["id"], unique=False)
    op.create_index(op.f("ix_stops_route_id"), "stops", ["route_id"], unique=False)
    op.create_index(op.f("ix_stops_stop_code"), "stops", ["stop_code"], unique=False)

    # 4. Bus Positions
    op.create_table(
        "bus_positions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bus_id", sa.Integer(), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("speed", sa.Float(), server_default=sa.text("0.0"), nullable=False),
        sa.Column("heading", sa.Float(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["bus_id"], ["buses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_bus_positions_id"), "bus_positions", ["id"], unique=False)
    op.create_index(op.f("ix_bus_positions_bus_id"), "bus_positions", ["bus_id"], unique=False)
    op.create_index(op.f("ix_bus_positions_timestamp"), "bus_positions", ["timestamp"], unique=False)

    # 5. Passenger Loads
    op.create_table(
        "passenger_loads",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bus_id", sa.Integer(), nullable=False),
        sa.Column("stop_id", sa.Integer(), nullable=True),
        sa.Column("current_load", sa.Integer(), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("load_factor", sa.Float(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["bus_id"], ["buses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["stop_id"], ["stops.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_passenger_loads_id"), "passenger_loads", ["id"], unique=False)
    op.create_index(op.f("ix_passenger_loads_bus_id"), "passenger_loads", ["bus_id"], unique=False)
    op.create_index(op.f("ix_passenger_loads_stop_id"), "passenger_loads", ["stop_id"], unique=False)
    op.create_index(op.f("ix_passenger_loads_timestamp"), "passenger_loads", ["timestamp"], unique=False)


def downgrade() -> None:
    op.drop_table("passenger_loads")
    op.drop_table("bus_positions")
    op.drop_table("stops")
    op.drop_table("buses")
    op.drop_table("routes")
