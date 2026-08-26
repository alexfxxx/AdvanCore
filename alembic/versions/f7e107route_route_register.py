"""route register"""
from alembic import op
import sqlalchemy as sa
revision="f7e107route"; down_revision="e6e106cust"; branch_labels=None; depends_on=None
def upgrade():
    op.create_table("routes",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("route_code",sa.String(40),nullable=False),sa.Column("origin",sa.String(160),nullable=False),sa.Column("destination",sa.String(160),nullable=False),sa.Column("status",sa.String(16),nullable=False,server_default="active"),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False),sa.CheckConstraint("status IN ('active', 'inactive')",name="ck_routes_status"),sa.UniqueConstraint("route_code",name="uq_routes_route_code"))
def downgrade(): op.drop_table("routes")
