"""fuel intelligence and recurring-service surcharge rules

Revision ID: f6e188fuel
Revises: f5e185payroll
Create Date: 2026-09-03
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "f6e188fuel"
down_revision: str | Sequence[str] | None = "f5e185payroll"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fuel_market_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("observed_on", sa.Date(), nullable=False),
        sa.Column("shell_price_per_litre", sa.Numeric(10, 4), nullable=False),
        sa.Column("spc_price_per_litre", sa.Numeric(10, 4), nullable=False),
        sa.Column("benchmark_price_per_litre", sa.Numeric(10, 4), nullable=False),
        sa.Column("shell_source_updated_at", sa.String(80), nullable=False),
        sa.Column("spc_source_updated_at", sa.String(80), nullable=False),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("observed_on", name="uq_fuel_market_snapshots_observed_on"),
        sa.CheckConstraint("shell_price_per_litre > 0", name="ck_fuel_market_shell_price"),
        sa.CheckConstraint("spc_price_per_litre > 0", name="ck_fuel_market_spc_price"),
        sa.CheckConstraint("benchmark_price_per_litre > 0", name="ck_fuel_market_benchmark_price"),
    )
    op.create_table(
        "fuel_market_refresh_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_failure_code", sa.String(40), nullable=True),
        sa.Column("last_failure_summary", sa.String(240), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("id = 1", name="ck_fuel_market_refresh_singleton"),
        sa.CheckConstraint("consecutive_failures >= 0", name="ck_fuel_market_refresh_failures"),
    )
    op.create_table(
        "recurring_service_fuel_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("recurring_service_id", sa.Integer(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("baseline_price_per_litre", sa.Numeric(10, 4), nullable=False),
        sa.Column("fuel_cost_share_percent", sa.Numeric(7, 4), nullable=False),
        sa.Column("tolerance_percent", sa.Numeric(7, 4), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["recurring_service_id"], ["recurring_services.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("recurring_service_id", "effective_from", name="uq_recurring_service_fuel_rule_effective"),
        sa.CheckConstraint("baseline_price_per_litre > 0", name="ck_fuel_rule_baseline"),
        sa.CheckConstraint("fuel_cost_share_percent >= 0 AND fuel_cost_share_percent <= 100", name="ck_fuel_rule_cost_share"),
        sa.CheckConstraint("tolerance_percent >= 0 AND tolerance_percent <= 100", name="ck_fuel_rule_tolerance"),
        sa.CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="ck_fuel_rule_effective_dates"),
    )


def downgrade() -> None:
    op.drop_table("recurring_service_fuel_rules")
    op.drop_table("fuel_market_refresh_state")
    op.drop_table("fuel_market_snapshots")
