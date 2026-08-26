"""trip assignments

Revision ID: b9e109assign
Revises: a8e108trip
"""
from alembic import op
import sqlalchemy as sa
revision="b9e109assign"; down_revision="a8e108trip"; branch_labels=None; depends_on=None
def upgrade():
    op.create_table("trip_assignments",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("trip_id",sa.Integer(),sa.ForeignKey("trips.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("vehicle_id",sa.Integer(),sa.ForeignKey("vehicles.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("driver_id",sa.Integer(),sa.ForeignKey("drivers.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("status",sa.String(16),nullable=False,server_default="assigned"),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False),
        sa.CheckConstraint("status IN ('assigned', 'released')",name="ck_trip_assignments_status"),
        sa.UniqueConstraint("trip_id",name="uq_trip_assignments_trip_id"))
def downgrade(): op.drop_table("trip_assignments")
