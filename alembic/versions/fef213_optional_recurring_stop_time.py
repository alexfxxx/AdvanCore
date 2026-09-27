"""allow recurring stops without an exact time

Revision ID: fef213nostoptime
Revises: fee212subpay
Create Date: 2026-09-10
"""

from collections.abc import Sequence

from alembic import op

revision: str = "fef213nostoptime"
down_revision: str | Sequence[str] | None = "fee212subpay"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("recurring_service_stops", "scheduled_time", nullable=True)


def downgrade() -> None:
    op.execute("DELETE FROM recurring_service_stops WHERE scheduled_time IS NULL")
    op.alter_column("recurring_service_stops", "scheduled_time", nullable=False)
