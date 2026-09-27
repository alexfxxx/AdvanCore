"""protected local vehicle document metadata

Revision ID: fbe193vehdoc
Revises: fae192assign
Create Date: 2026-09-05
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "fbe193vehdoc"
down_revision: str | Sequence[str] | None = "fae192assign"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vehicle_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("document_type", sa.String(24), nullable=False),
        sa.Column("storage_filename", sa.String(200), nullable=False, unique=True),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("sha256_hex", sa.String(64), nullable=False, unique=True),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("mime_type", sa.String(80), nullable=False, server_default="application/pdf"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("vehicle_id", "document_type", name="uq_vehicle_document_type"),
        sa.CheckConstraint("document_type IN ('logcard')", name="ck_vehicle_document_type"),
        sa.CheckConstraint("byte_size > 0", name="ck_vehicle_document_size"),
    )


def downgrade() -> None:
    op.drop_table("vehicle_documents")
