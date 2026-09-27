"""fleet tyre and fuel operating metrics

Revision ID: fce200fleetmetrics
Revises: fbe193vehdoc
Create Date: 2026-09-05
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "fce200fleetmetrics"
down_revision: str | Sequence[str] | None = "fbe193vehdoc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vehicles", sa.Column("tyre_cost", sa.Numeric(12, 2), nullable=True))
    op.add_column("vehicles", sa.Column("tyre_lifespan_km", sa.Integer(), nullable=True))
    op.add_column("vehicles", sa.Column("fuel_consumption_km_per_liter", sa.Numeric(8, 3), nullable=True))
    op.create_check_constraint("ck_vehicles_tyre_cost", "vehicles", "tyre_cost IS NULL OR tyre_cost >= 0")
    op.create_check_constraint("ck_vehicles_tyre_lifespan", "vehicles", "tyre_lifespan_km IS NULL OR tyre_lifespan_km > 0")
    op.create_check_constraint("ck_vehicles_fuel_consumption", "vehicles", "fuel_consumption_km_per_liter IS NULL OR fuel_consumption_km_per_liter > 0")


def downgrade() -> None:
    op.drop_constraint("ck_vehicles_fuel_consumption", "vehicles", type_="check")
    op.drop_constraint("ck_vehicles_tyre_lifespan", "vehicles", type_="check")
    op.drop_constraint("ck_vehicles_tyre_cost", "vehicles", type_="check")
    op.drop_column("vehicles", "fuel_consumption_km_per_liter")
    op.drop_column("vehicles", "tyre_lifespan_km")
    op.drop_column("vehicles", "tyre_cost")
