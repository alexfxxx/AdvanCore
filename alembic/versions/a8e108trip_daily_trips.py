"""daily trips"""
from alembic import op
import sqlalchemy as sa
revision="a8e108trip";down_revision="f7e107route";branch_labels=None;depends_on=None
def upgrade():
    op.create_table("trips",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("trip_reference",sa.String(40),nullable=False),sa.Column("route_id",sa.Integer(),sa.ForeignKey("routes.id",ondelete="RESTRICT"),nullable=False),sa.Column("service_date",sa.Date(),nullable=False),sa.Column("status",sa.String(16),nullable=False,server_default="planned"),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False),sa.CheckConstraint("status IN ('planned', 'completed', 'cancelled')",name="ck_trips_status"),sa.UniqueConstraint("trip_reference",name="uq_trips_reference"))
def downgrade():op.drop_table("trips")
