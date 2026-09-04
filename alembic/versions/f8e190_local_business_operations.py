"""local subcontractor, recurring assignment and maintenance registers

Revision ID: f8e190localops
Revises: f6e188fuel
Create Date: 2026-09-04
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "f8e190localops"
down_revision: str | Sequence[str] | None = "f6e188fuel"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subcontractors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_name", sa.String(160), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("status IN ('active', 'archived')", name="ck_subcontractors_status"),
    )
    op.create_table(
        "subcontractor_drivers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("subcontractor_id", sa.Integer(), sa.ForeignKey("subcontractors.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("contact_number", sa.String(40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_table(
        "subcontractor_vehicles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("subcontractor_id", sa.Integer(), sa.ForeignKey("subcontractors.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("vehicle_number", sa.String(32), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("subcontractor_id", "vehicle_number", name="uq_subcontractor_vehicle_number"),
    )
    op.create_table(
        "recurring_route_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("recurring_service_id", sa.Integer(), sa.ForeignKey("recurring_services.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("assignment_type", sa.String(20), nullable=False),
        sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("driver_id", sa.Integer(), sa.ForeignKey("drivers.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("subcontractor_vehicle_id", sa.Integer(), sa.ForeignKey("subcontractor_vehicles.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("subcontractor_driver_id", sa.Integer(), sa.ForeignKey("subcontractor_drivers.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("monthly_subcontractor_cost", sa.Numeric(12, 2), nullable=True),
        sa.Column("effective_start_date", sa.Date(), nullable=False),
        sa.Column("effective_end_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("remarks", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("assignment_type IN ('own_fleet', 'subcontractor')", name="ck_route_assignment_type"),
        sa.CheckConstraint("status IN ('active', 'ended')", name="ck_route_assignment_status"),
        sa.CheckConstraint("monthly_subcontractor_cost IS NULL OR monthly_subcontractor_cost >= 0", name="ck_route_assignment_monthly_cost"),
    )
    op.create_table(
        "maintenance_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("service_date", sa.Date(), nullable=False),
        sa.Column("vendor", sa.String(160), nullable=False),
        sa.Column("service_type", sa.String(120), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("remarks", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("amount > 0", name="ck_maintenance_amount_positive"),
    )


def downgrade() -> None:
    op.drop_table("maintenance_entries")
    op.drop_table("recurring_route_assignments")
    op.drop_table("subcontractor_vehicles")
    op.drop_table("subcontractor_drivers")
    op.drop_table("subcontractors")
