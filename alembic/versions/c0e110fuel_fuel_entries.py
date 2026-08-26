"""fuel entries

Revision ID: c0e110fuel
Revises: b9e109assign
"""
from alembic import op
import sqlalchemy as sa
revision="c0e110fuel"; down_revision="b9e109assign"; branch_labels=None; depends_on=None
def upgrade():
    op.create_table("fuel_entries",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("vehicle_id",sa.Integer(),sa.ForeignKey("vehicles.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("recorded_on",sa.Date(),nullable=False),
        sa.Column("litres",sa.Numeric(10,2),nullable=False),
        sa.Column("total_cost",sa.Numeric(12,2),nullable=True),
        sa.Column("odometer_km",sa.Numeric(12,1),nullable=True),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False),
        sa.CheckConstraint("litres > 0",name="ck_fuel_entries_litres_positive"),
        sa.CheckConstraint("total_cost IS NULL OR total_cost >= 0",name="ck_fuel_entries_total_cost_nonnegative"),
        sa.CheckConstraint("odometer_km IS NULL OR odometer_km >= 0",name="ck_fuel_entries_odometer_nonnegative"))
def downgrade(): op.drop_table("fuel_entries")
