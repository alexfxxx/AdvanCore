"""knowledge approval foundation

Revision ID: 3f61b4a9c2d7
Revises: 639d8b65223c
Create Date: 2026-08-25

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "3f61b4a9c2d7"
down_revision: str | Sequence[str] | None = "639d8b65223c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add nullable approval evidence and fail-closed consistency checks."""
    op.add_column(
        "knowledge_items",
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "knowledge_items",
        sa.Column("approved_by", sa.String(length=100), nullable=True),
    )
    op.create_check_constraint(
        "ck_knowledge_items_approval_fields_paired",
        "knowledge_items",
        "(approved_at IS NULL AND approved_by IS NULL) OR "
        "(approved_at IS NOT NULL AND approved_by IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_knowledge_items_approved_has_metadata",
        "knowledge_items",
        "status <> 'approved' OR "
        "(approved_at IS NOT NULL AND approved_by IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_knowledge_items_draft_unapproved",
        "knowledge_items",
        "status <> 'draft' OR "
        "(approved_at IS NULL AND approved_by IS NULL)",
    )
    op.create_check_constraint(
        "ck_knowledge_items_approver_nonblank",
        "knowledge_items",
        "approved_by IS NULL OR length(trim(approved_by)) > 0",
    )


def downgrade() -> None:
    """Remove the approval foundation without rewriting prior migrations."""
    op.drop_constraint(
        "ck_knowledge_items_approver_nonblank",
        "knowledge_items",
        type_="check",
    )
    op.drop_constraint(
        "ck_knowledge_items_draft_unapproved",
        "knowledge_items",
        type_="check",
    )
    op.drop_constraint(
        "ck_knowledge_items_approved_has_metadata",
        "knowledge_items",
        type_="check",
    )
    op.drop_constraint(
        "ck_knowledge_items_approval_fields_paired",
        "knowledge_items",
        type_="check",
    )
    op.drop_column("knowledge_items", "approved_by")
    op.drop_column("knowledge_items", "approved_at")
