"""store confirmed paid counts and outstanding instalment balances

Revision ID: ffg215balances
Revises: fff214remaining
Create Date: 2026-09-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ffg215balances"
down_revision: str | Sequence[str] | None = "fff214remaining"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vehicles", sa.Column("confirmed_instalments_paid", sa.Integer(), nullable=True))
    op.add_column("vehicles", sa.Column("confirmed_remaining_balance", sa.Numeric(12, 2), nullable=True))
    op.create_check_constraint(
        "ck_vehicles_confirmed_instalments_paid",
        "vehicles",
        "confirmed_instalments_paid IS NULL OR confirmed_instalments_paid >= 0",
    )
    op.create_check_constraint(
        "ck_vehicles_confirmed_remaining_balance",
        "vehicles",
        "confirmed_remaining_balance IS NULL OR confirmed_remaining_balance >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_vehicles_confirmed_remaining_balance", "vehicles", type_="check")
    op.drop_constraint("ck_vehicles_confirmed_instalments_paid", "vehicles", type_="check")
    op.drop_column("vehicles", "confirmed_remaining_balance")
    op.drop_column("vehicles", "confirmed_instalments_paid")
