from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from advancore.models.base import Base, TimestampMixin


class KnowledgeItem(TimestampMixin, Base):
    __tablename__ = "knowledge_items"
    __table_args__ = (
        CheckConstraint(
            "(approved_at IS NULL AND approved_by IS NULL) OR "
            "(approved_at IS NOT NULL AND approved_by IS NOT NULL)",
            name="ck_knowledge_items_approval_fields_paired",
        ),
        CheckConstraint(
            "status <> 'approved' OR "
            "(approved_at IS NOT NULL AND approved_by IS NOT NULL)",
            name="ck_knowledge_items_approved_has_metadata",
        ),
        CheckConstraint(
            "status <> 'draft' OR "
            "(approved_at IS NULL AND approved_by IS NULL)",
            name="ck_knowledge_items_draft_unapproved",
        ),
        CheckConstraint(
            "approved_by IS NULL OR length(trim(approved_by)) > 0",
            name="ck_knowledge_items_approver_nonblank",
        ),
        CheckConstraint(
            "replaces_knowledge_item_id IS NULL OR "
            "replaces_knowledge_item_id <> id",
            name="ck_knowledge_items_not_self_replacing",
        ),
        CheckConstraint(
            "status <> 'superseded' OR "
            "(approved_at IS NOT NULL AND approved_by IS NOT NULL)",
            name="ck_knowledge_items_superseded_has_metadata",
        ),
        Index(
            "uq_knowledge_items_open_replacement",
            "replaces_knowledge_item_id",
            unique=True,
            postgresql_where=text(
                "replaces_knowledge_item_id IS NOT NULL AND status <> 'archived'"
            ),
            sqlite_where=text(
                "replaces_knowledge_item_id IS NOT NULL AND status <> 'archived'"
            ),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id"),
        nullable=True,
    )

    replaces_knowledge_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_items.id", ondelete="RESTRICT"),
        nullable=True,
    )

    title: Mapped[str] = mapped_column(
        String(300),
        nullable=False,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        default="draft",
        nullable=False,
    )

    source_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    source_reference: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    approved_by: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
