"""subcontractor cost bundles and accounting-month payments

Revision ID: fee212subpay
Revises: fde211drivervehicle
Create Date: 2026-09-10
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "fee212subpay"
down_revision: str | Sequence[str] | None = "fde211drivervehicle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("recurring_route_assignments", sa.Column("cost_bundle_reference", sa.String(80), nullable=True))
    op.create_table(
        "subcontractor_payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("subcontractor_id", sa.Integer(), sa.ForeignKey("subcontractors.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("cost_bundle_reference", sa.String(80), nullable=False),
        sa.Column("accounting_month", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("expected_payment_date", sa.Date(), nullable=True),
        sa.Column("payment_status", sa.String(16), nullable=False, server_default="unpaid"),
        sa.Column("payment_date", sa.Date(), nullable=True),
        sa.Column("remarks", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("subcontractor_id", "cost_bundle_reference", "accounting_month", name="uq_subcontractor_payment_month"),
        sa.CheckConstraint("amount > 0", name="ck_subcontractor_payment_amount"),
        sa.CheckConstraint("payment_status IN ('unpaid', 'paid')", name="ck_subcontractor_payment_status"),
    )


def downgrade() -> None:
    op.drop_table("subcontractor_payments")
    op.drop_column("recurring_route_assignments", "cost_bundle_reference")
