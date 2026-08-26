"""driver register

Revision ID: d5e105driver
Revises: c4e104fleet1
"""
from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa
revision: str = "d5e105driver"
down_revision: str | Sequence[str] | None = "c4e104fleet1"
branch_labels = None
depends_on = None
def upgrade() -> None:
    op.create_table("drivers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("employee_reference", sa.String(40), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('active', 'unavailable', 'retired')", name="ck_drivers_status"),
        sa.UniqueConstraint("employee_reference", name="uq_drivers_employee_reference"),
    )
def downgrade() -> None: op.drop_table("drivers")
