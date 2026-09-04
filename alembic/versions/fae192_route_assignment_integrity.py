"""enforce one active recurring route assignment

Revision ID: fae192assign
Revises: f9e191finance
Create Date: 2026-09-04
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "fae192assign"
down_revision: str | Sequence[str] | None = "f9e191finance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_recurring_route_assignment_active",
        "recurring_route_assignments",
        ["recurring_service_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index("uq_recurring_route_assignment_active", table_name="recurring_route_assignments")
