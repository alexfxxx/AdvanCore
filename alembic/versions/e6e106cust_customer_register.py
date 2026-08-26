"""customer register

Revision ID: e6e106cust
Revises: d5e105driver
"""
from alembic import op
import sqlalchemy as sa
revision = "e6e106cust"; down_revision = "d5e105driver"; branch_labels = None; depends_on = None
def upgrade():
    op.create_table("customers", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(160), nullable=False), sa.Column("customer_reference", sa.String(40), nullable=True), sa.Column("status", sa.String(16), nullable=False, server_default="active"), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.CheckConstraint("status IN ('active', 'inactive')", name="ck_customers_status"), sa.UniqueConstraint("customer_reference", name="uq_customers_customer_reference"))
def downgrade(): op.drop_table("customers")
