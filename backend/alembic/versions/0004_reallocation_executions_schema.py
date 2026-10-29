"""Stage Execution Migration: reallocation_executions

Creates the reallocation_executions table for recording the formal execution
and runtime dispatch of approved bus route reassignments, and adds execution
status tracking columns to reallocation_reviews.

Revision ID: 0004_executions
Revises: 0003_notifications
Create Date: 2026-10-13
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0004_executions"
down_revision: Union[str, None] = "0003_notifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create reallocation_executions table
    op.create_table(
        "reallocation_executions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("recommendation_id", sa.String(length=100), nullable=False),
        sa.Column("review_id", sa.Integer(), nullable=True),
        sa.Column("bus_id", sa.Integer(), nullable=False),
        sa.Column("bus_number", sa.String(length=50), nullable=False),
        sa.Column("source_route_id", sa.Integer(), nullable=False),
        sa.Column("source_route_number", sa.String(length=50), nullable=False),
        sa.Column("target_route_id", sa.Integer(), nullable=False),
        sa.Column("target_route_number", sa.String(length=50), nullable=False),
        sa.Column("dispatcher_id", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["review_id"], ["reallocation_reviews.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["bus_id"], ["buses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_route_id"], ["routes.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["target_route_id"], ["routes.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_reallocation_executions_id"),
        "reallocation_executions",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reallocation_executions_recommendation_id"),
        "reallocation_executions",
        ["recommendation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reallocation_executions_review_id"),
        "reallocation_executions",
        ["review_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reallocation_executions_bus_id"),
        "reallocation_executions",
        ["bus_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reallocation_executions_source_route_id"),
        "reallocation_executions",
        ["source_route_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reallocation_executions_target_route_id"),
        "reallocation_executions",
        ["target_route_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reallocation_executions_status"),
        "reallocation_executions",
        ["status"],
        unique=False,
    )

    # 2. Add execution tracking columns to reallocation_reviews
    op.add_column(
        "reallocation_reviews",
        sa.Column(
            "execution_status",
            sa.String(length=50),
            server_default="NOT_EXECUTED",
            nullable=True,
        ),
    )
    op.add_column(
        "reallocation_reviews",
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("reallocation_reviews", "executed_at")
    op.drop_column("reallocation_reviews", "execution_status")

    op.drop_index(
        op.f("ix_reallocation_executions_status"),
        table_name="reallocation_executions",
    )
    op.drop_index(
        op.f("ix_reallocation_executions_target_route_id"),
        table_name="reallocation_executions",
    )
    op.drop_index(
        op.f("ix_reallocation_executions_source_route_id"),
        table_name="reallocation_executions",
    )
    op.drop_index(
        op.f("ix_reallocation_executions_bus_id"),
        table_name="reallocation_executions",
    )
    op.drop_index(
        op.f("ix_reallocation_executions_review_id"),
        table_name="reallocation_executions",
    )
    op.drop_index(
        op.f("ix_reallocation_executions_recommendation_id"),
        table_name="reallocation_executions",
    )
    op.drop_index(
        op.f("ix_reallocation_executions_id"),
        table_name="reallocation_executions",
    )
    op.drop_table("reallocation_executions")
