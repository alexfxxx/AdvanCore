"""vehicle register

Revision ID: c4e104fleet1
Revises: a94f8b17d6e2
Create Date: 2026-08-27
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "c4e104fleet1"
down_revision: str | Sequence[str] | None = "a94f8b17d6e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vehicles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("registration_number", sa.String(32), nullable=False),
        sa.Column("make_model", sa.String(120), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'out_of_service', 'retired')",
            name="ck_vehicles_status",
        ),
        sa.UniqueConstraint("registration_number", name="uq_vehicles_registration_number"),
    )


def downgrade() -> None:
    op.drop_table("vehicles")
