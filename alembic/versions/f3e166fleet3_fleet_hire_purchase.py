"""fleet hire purchase source fields

Revision ID: f3e166fleet3
Revises: e2f119fleet2
Create Date: 2026-08-30
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "f3e166fleet3"
down_revision: str | Sequence[str] | None = "e2f119fleet2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = (
        sa.Column("finance_company", sa.String(120), nullable=True),
        sa.Column("original_loan_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("monthly_instalment", sa.Numeric(12, 2), nullable=True),
        sa.Column("loan_start_date", sa.Date(), nullable=True),
        sa.Column("loan_term_months", sa.Integer(), nullable=True),
    )
    for column in columns:
        op.add_column("vehicles", column)
    op.create_check_constraint(
        "ck_vehicles_original_loan_amount",
        "vehicles",
        "original_loan_amount IS NULL OR original_loan_amount >= 0",
    )
    op.create_check_constraint(
        "ck_vehicles_monthly_instalment",
        "vehicles",
        "monthly_instalment IS NULL OR monthly_instalment >= 0",
    )
    op.create_check_constraint(
        "ck_vehicles_loan_term_months",
        "vehicles",
        "loan_term_months IS NULL OR loan_term_months > 0",
    )


def downgrade() -> None:
    for name in (
        "ck_vehicles_loan_term_months",
        "ck_vehicles_monthly_instalment",
        "ck_vehicles_original_loan_amount",
    ):
        op.drop_constraint(name, "vehicles", type_="check")
    for name in (
        "loan_term_months",
        "loan_start_date",
        "monthly_instalment",
        "original_loan_amount",
        "finance_company",
    ):
        op.drop_column("vehicles", name)
