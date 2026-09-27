"""store lender-confirmed remaining vehicle instalments

Revision ID: fff214remaining
Revises: fef213nostoptime
Create Date: 2026-09-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "fff214remaining"
down_revision: str | Sequence[str] | None = "fef213nostoptime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vehicles", sa.Column("confirmed_remaining_instalments", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_vehicles_confirmed_remaining_instalments",
        "vehicles",
        "confirmed_remaining_instalments IS NULL OR confirmed_remaining_instalments >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_vehicles_confirmed_remaining_instalments", "vehicles", type_="check")
    op.drop_column("vehicles", "confirmed_remaining_instalments")
