"""knowledge replacement history

Revision ID: a94f8b17d6e2
Revises: 3f61b4a9c2d7
Create Date: 2026-08-25

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "a94f8b17d6e2"
down_revision: str | Sequence[str] | None = "3f61b4a9c2d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add nullable, forward-only replacement lineage without rewriting rows."""
    op.add_column(
        "knowledge_items",
        sa.Column("replaces_knowledge_item_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_knowledge_items_replaces_knowledge_item_id",
        "knowledge_items",
        "knowledge_items",
        ["replaces_knowledge_item_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_knowledge_items_not_self_replacing",
        "knowledge_items",
        "replaces_knowledge_item_id IS NULL OR replaces_knowledge_item_id <> id",
    )
    op.create_check_constraint(
        "ck_knowledge_items_superseded_has_metadata",
        "knowledge_items",
        "status <> 'superseded' OR "
        "(approved_at IS NOT NULL AND approved_by IS NOT NULL)",
    )
    op.create_index(
        "uq_knowledge_items_open_replacement",
        "knowledge_items",
        ["replaces_knowledge_item_id"],
        unique=True,
        postgresql_where=sa.text(
            "replaces_knowledge_item_id IS NOT NULL AND status <> 'archived'"
        ),
    )


def downgrade() -> None:
    """Remove replacement lineage without changing prior migration history."""
    op.drop_index(
        "uq_knowledge_items_open_replacement",
        table_name="knowledge_items",
    )
    op.drop_constraint(
        "ck_knowledge_items_superseded_has_metadata",
        "knowledge_items",
        type_="check",
    )
    op.drop_constraint(
        "ck_knowledge_items_not_self_replacing",
        "knowledge_items",
        type_="check",
    )
    op.drop_constraint(
        "fk_knowledge_items_replaces_knowledge_item_id",
        "knowledge_items",
        type_="foreignkey",
    )
    op.drop_column("knowledge_items", "replaces_knowledge_item_id")
