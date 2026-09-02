"""recurring customer services

Revision ID: f4e183recurring
Revises: f3e166fleet3
Create Date: 2026-09-02
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "f4e183recurring"
down_revision: str | Sequence[str] | None = "f3e166fleet3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recurring_services",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("route_id", sa.Integer(), nullable=False),
        sa.Column("service_reference", sa.String(40), nullable=False),
        sa.Column("vehicle_requirement", sa.String(200), nullable=True),
        sa.Column("monthly_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("effective_start_date", sa.Date(), nullable=False),
        sa.Column("effective_end_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("replaces_recurring_service_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["route_id"], ["routes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["replaces_recurring_service_id"], ["recurring_services.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "customer_id",
            "service_reference",
            "effective_start_date",
            name="uq_recurring_services_customer_reference_start",
        ),
    )
    op.create_check_constraint(
        "ck_recurring_services_status",
        "recurring_services",
        "status IN ('active', 'paused', 'archived')",
    )
    op.create_check_constraint(
        "ck_recurring_services_monthly_amount",
        "recurring_services",
        "monthly_amount >= 0",
    )
    op.create_check_constraint(
        "ck_recurring_services_currency_code",
        "recurring_services",
        "LENGTH(currency_code) = 3",
    )
    op.create_check_constraint(
        "ck_recurring_services_effective_dates",
        "recurring_services",
        "effective_end_date IS NULL OR effective_end_date >= effective_start_date",
    )

    op.create_table(
        "recurring_service_days",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("recurring_service_id", sa.Integer(), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["recurring_service_id"], ["recurring_services.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "recurring_service_id",
            "stop_order",
            name="uq_recurring_service_stops_service_order",
        ),
        sa.UniqueConstraint("recurring_service_id", "weekday", name="uq_recurring_service_days_service_weekday"),
    )
    op.create_check_constraint(
        "ck_recurring_service_days_weekday",
        "recurring_service_days",
        "weekday >= 0 AND weekday <= 6",
    )

    op.create_table(
        "recurring_service_stops",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("recurring_service_id", sa.Integer(), nullable=False),
        sa.Column("stop_order", sa.Integer(), nullable=False),
        sa.Column("location_name", sa.String(160), nullable=False),
        sa.Column("scheduled_time", sa.Time(), nullable=False),
        sa.ForeignKeyConstraint(["recurring_service_id"], ["recurring_services.id"], ondelete="CASCADE"),
    )
    op.create_check_constraint(
        "ck_recurring_service_stops_stop_order",
        "recurring_service_stops",
        "stop_order >= 0",
    )


def downgrade() -> None:
    op.drop_table("recurring_service_stops")
    op.drop_table("recurring_service_days")
    for name in (
        "ck_recurring_services_effective_dates",
        "ck_recurring_services_currency_code",
        "ck_recurring_services_monthly_amount",
        "ck_recurring_services_status",
    ):
        op.drop_constraint(name, "recurring_services", type_="check")
    op.drop_table("recurring_services")
