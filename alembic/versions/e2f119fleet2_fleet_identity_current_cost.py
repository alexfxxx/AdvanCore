"""fleet identity and current cost foundation

Revision ID: e2f119fleet2
Revises: d1e111fin
Create Date: 2026-08-27
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "e2f119fleet2"
down_revision: str | Sequence[str] | None = "d1e111fin"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "legal_entities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('active', 'inactive')", name="ck_legal_entities_status"),
        sa.UniqueConstraint("name", name="uq_legal_entities_name"),
    )
    columns = (
        sa.Column("registered_owner_id", sa.Integer(), nullable=True),
        sa.Column("manufacture_year", sa.Integer(), nullable=True),
        sa.Column("passenger_capacity", sa.Integer(), nullable=True),
        sa.Column("vehicle_type", sa.String(16), nullable=True),
        sa.Column("propellant", sa.String(40), nullable=True),
        sa.Column("scheme", sa.String(80), nullable=True),
        sa.Column("chassis_number", sa.String(80), nullable=True),
        sa.Column("engine_number", sa.String(80), nullable=True),
        sa.Column("original_registration_date", sa.Date(), nullable=True),
        sa.Column("lifespan_expiry", sa.Date(), nullable=True),
        sa.Column("coe_expiry", sa.Date(), nullable=True),
        sa.Column("primary_colour", sa.String(40), nullable=True),
        sa.Column("unladen_weight_kg", sa.Numeric(10, 2), nullable=True),
        sa.Column("maximum_laden_weight_kg", sa.Numeric(10, 2), nullable=True),
        sa.Column("parking_provider", sa.String(120), nullable=True),
        sa.Column("parking_location", sa.String(200), nullable=True),
        sa.Column("parking_monthly_cost", sa.Numeric(12, 2), nullable=True),
        sa.Column("insurance_provider", sa.String(120), nullable=True),
        sa.Column("insurance_annual_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("road_tax_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("road_tax_period_months", sa.Integer(), nullable=True),
    )
    for column in columns: op.add_column("vehicles", column)
    op.create_foreign_key("fk_vehicles_registered_owner_id", "vehicles", "legal_entities", ["registered_owner_id"], ["id"], ondelete="RESTRICT")
    checks = {
        "ck_vehicles_type": "vehicle_type IS NULL OR vehicle_type IN ('Bus', 'lorry', 'car')",
        "ck_vehicles_passenger_capacity_positive": "passenger_capacity IS NULL OR passenger_capacity > 0",
        "ck_vehicles_manufacture_year": "manufacture_year IS NULL OR manufacture_year BETWEEN 1886 AND 9999",
        "ck_vehicles_unladen_weight": "unladen_weight_kg IS NULL OR unladen_weight_kg >= 0",
        "ck_vehicles_maximum_laden_weight": "maximum_laden_weight_kg IS NULL OR maximum_laden_weight_kg >= 0",
        "ck_vehicles_parking_cost": "parking_monthly_cost IS NULL OR parking_monthly_cost >= 0",
        "ck_vehicles_insurance_amount": "insurance_annual_amount IS NULL OR insurance_annual_amount >= 0",
        "ck_vehicles_road_tax_amount": "road_tax_amount IS NULL OR road_tax_amount >= 0",
        "ck_vehicles_road_tax_period": "(road_tax_amount IS NULL AND road_tax_period_months IS NULL) OR (road_tax_amount IS NOT NULL AND road_tax_period_months IN (6, 12))",
    }
    for name, condition in checks.items(): op.create_check_constraint(name, "vehicles", condition)

def downgrade() -> None:
    for name in ("ck_vehicles_road_tax_period", "ck_vehicles_road_tax_amount", "ck_vehicles_insurance_amount", "ck_vehicles_parking_cost", "ck_vehicles_maximum_laden_weight", "ck_vehicles_unladen_weight", "ck_vehicles_manufacture_year", "ck_vehicles_passenger_capacity_positive", "ck_vehicles_type"):
        op.drop_constraint(name, "vehicles", type_="check")
    op.drop_constraint("fk_vehicles_registered_owner_id", "vehicles", type_="foreignkey")
    for name in ("road_tax_period_months", "road_tax_amount", "insurance_annual_amount", "insurance_provider", "parking_monthly_cost", "parking_location", "parking_provider", "maximum_laden_weight_kg", "unladen_weight_kg", "primary_colour", "coe_expiry", "lifespan_expiry", "original_registration_date", "engine_number", "chassis_number", "scheme", "propellant", "vehicle_type", "passenger_capacity", "manufacture_year", "registered_owner_id"):
        op.drop_column("vehicles", name)
    op.drop_table("legal_entities")
