"""accounting month and optional payment timing

Revision ID: f9e191finance
Revises: f8e190localops
Create Date: 2026-09-04
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "f9e191finance"
down_revision: str | Sequence[str] | None = "f8e190localops"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("financial_entries", sa.Column("vehicle_id", sa.Integer(), nullable=True))
    op.add_column("financial_entries", sa.Column("accounting_month", sa.Date(), nullable=True))
    op.add_column("financial_entries", sa.Column("expected_payment_date", sa.Date(), nullable=True))
    op.add_column("financial_entries", sa.Column("payment_status", sa.String(16), nullable=False, server_default="unpaid"))
    op.add_column("financial_entries", sa.Column("payment_date", sa.Date(), nullable=True))
    op.add_column("financial_entries", sa.Column("category", sa.String(40), nullable=True))
    op.create_foreign_key("fk_financial_entries_vehicle", "financial_entries", "vehicles", ["vehicle_id"], ["id"], ondelete="RESTRICT")
    op.execute("UPDATE financial_entries SET accounting_month = date_trunc('month', entry_date)::date")
    op.alter_column("financial_entries", "accounting_month", nullable=False)
    op.create_check_constraint("ck_financial_entries_payment_status", "financial_entries", "payment_status IN ('unpaid', 'paid')")


def downgrade() -> None:
    op.drop_constraint("ck_financial_entries_payment_status", "financial_entries", type_="check")
    op.drop_constraint("fk_financial_entries_vehicle", "financial_entries", type_="foreignkey")
    for column in ("category", "payment_date", "payment_status", "expected_payment_date", "accounting_month", "vehicle_id"):
        op.drop_column("financial_entries", column)
