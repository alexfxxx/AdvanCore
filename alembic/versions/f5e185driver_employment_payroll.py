"""driver employment and payroll history

Revision ID: f5e185payroll
Revises: f4e183recurring
Create Date: 2026-09-02
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "f5e185payroll"
down_revision: str | Sequence[str] | None = "f4e183recurring"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "driver_employment_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("driver_id", sa.Integer(), nullable=False),
        sa.Column("effective_month", sa.Date(), nullable=False),
        sa.Column("worker_category", sa.String(24), nullable=False),
        sa.Column("basic_salary", sa.Numeric(12, 2), nullable=False),
        sa.Column("employer_cpf_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("monthly_levy_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("monthly_allowance", sa.Numeric(12, 2), nullable=True),
        sa.Column("employment_status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["driver_id"], ["drivers.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("driver_id", "effective_month", name="uq_driver_employment_driver_month"),
        sa.CheckConstraint("worker_category IN ('local_pr', 'foreign_levy')", name="ck_driver_employment_worker_category"),
        sa.CheckConstraint("employment_status IN ('active', 'inactive')", name="ck_driver_employment_status"),
        sa.CheckConstraint("basic_salary >= 0", name="ck_driver_employment_basic_salary"),
        sa.CheckConstraint("employer_cpf_amount IS NULL OR employer_cpf_amount >= 0", name="ck_driver_employment_cpf_amount"),
        sa.CheckConstraint("monthly_levy_amount IS NULL OR monthly_levy_amount >= 0", name="ck_driver_employment_levy_amount"),
        sa.CheckConstraint("monthly_allowance IS NULL OR monthly_allowance >= 0", name="ck_driver_employment_allowance"),
        sa.CheckConstraint(
            "(worker_category = 'local_pr' AND monthly_levy_amount IS NULL) OR "
            "(worker_category = 'foreign_levy' AND employer_cpf_amount IS NULL)",
            name="ck_driver_employment_cost_category",
        ),
    )


def downgrade() -> None:
    op.drop_table("driver_employment_records")
