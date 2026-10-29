"""Stage 7 Schema Migration: reallocation_reviews

Creates the reallocation_reviews table for storing dispatcher decisions (APPROVED,
REJECTED, DEFERRED) on Stage 5 rule-based fleet reallocation recommendations.

Revision ID: 0002_reviews
Revises: 0001_initial
Create Date: 2026-10-12
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0002_reviews"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reallocation_reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("recommendation_id", sa.String(length=100), nullable=False),
        sa.Column("decision", sa.String(length=50), nullable=False),
        sa.Column("dispatcher_id", sa.String(length=100), nullable=True),
        sa.Column("target_route_id", sa.Integer(), nullable=True),
        sa.Column("target_route_number", sa.String(length=50), nullable=True),
        sa.Column("source_route_id", sa.Integer(), nullable=True),
        sa.Column("source_route_number", sa.String(length=50), nullable=True),
        sa.Column("candidate_bus_id", sa.Integer(), nullable=True),
        sa.Column("candidate_bus_number", sa.String(length=50), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("priority", sa.String(length=50), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["target_route_id"], ["routes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_route_id"], ["routes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["candidate_bus_id"], ["buses.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_reallocation_reviews_id"), "reallocation_reviews", ["id"], unique=False)
    op.create_index(
        op.f("ix_reallocation_reviews_recommendation_id"),
        "reallocation_reviews",
        ["recommendation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reallocation_reviews_decision"),
        "reallocation_reviews",
        ["decision"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reallocation_reviews_target_route_id"),
        "reallocation_reviews",
        ["target_route_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reallocation_reviews_source_route_id"),
        "reallocation_reviews",
        ["source_route_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reallocation_reviews_candidate_bus_id"),
        "reallocation_reviews",
        ["candidate_bus_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_reallocation_reviews_candidate_bus_id"), table_name="reallocation_reviews")
    op.drop_index(op.f("ix_reallocation_reviews_source_route_id"), table_name="reallocation_reviews")
    op.drop_index(op.f("ix_reallocation_reviews_target_route_id"), table_name="reallocation_reviews")
    op.drop_index(op.f("ix_reallocation_reviews_decision"), table_name="reallocation_reviews")
    op.drop_index(op.f("ix_reallocation_reviews_recommendation_id"), table_name="reallocation_reviews")
    op.drop_index(op.f("ix_reallocation_reviews_id"), table_name="reallocation_reviews")
    op.drop_table("reallocation_reviews")
