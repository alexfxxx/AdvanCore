"""reusable driver vehicle links

Revision ID: fde211drivervehicle
Revises: fce200fleetmetrics
"""
from alembic import op
import sqlalchemy as sa

revision = "fde211drivervehicle"
down_revision = "fce200fleetmetrics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "driver_vehicle_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("driver_id", sa.Integer(), sa.ForeignKey("drivers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("driver_id", "vehicle_id", name="uq_driver_vehicle_link"),
        sa.CheckConstraint("status IN ('active', 'inactive')", name="ck_driver_vehicle_link_status"),
    )


def downgrade() -> None:
    op.drop_table("driver_vehicle_links")
