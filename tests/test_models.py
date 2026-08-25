"""Smoke and metadata tests for the AdvanCore model foundation."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from advancore.models import Base, KnowledgeItem


def test_model_package_imports():
    """All public models and Base import successfully from advancore.models."""
    from advancore.models import (
        ActivityLog,
        Base,
        KnowledgeItem,
        Project,
        SystemSetting,
    )

    assert Base is not None
    assert Project is not None
    assert KnowledgeItem is not None
    assert ActivityLog is not None
    assert SystemSetting is not None


def test_expected_model_tables_registered():
    """The four existing model tables are present in Base.metadata."""
    from advancore.models import Base

    table_names = set(Base.metadata.tables.keys())

    assert "projects" in table_names
    assert "knowledge_items" in table_names
    assert "activity_logs" in table_names
    assert "system_settings" in table_names


def test_knowledge_model_registers_bounded_approval_metadata():
    table = KnowledgeItem.__table__
    assert table.c.approved_at.nullable is True
    assert table.c.approved_at.type.timezone is True
    assert table.c.approved_by.nullable is True
    assert table.c.approved_by.type.length == 100
    assert table.c.replaces_knowledge_item_id.nullable is True
    assert next(iter(table.c.replaces_knowledge_item_id.foreign_keys)).target_fullname == (
        "knowledge_items.id"
    )
    assert {constraint.name for constraint in table.constraints} >= {
        "ck_knowledge_items_approval_fields_paired",
        "ck_knowledge_items_approved_has_metadata",
        "ck_knowledge_items_draft_unapproved",
        "ck_knowledge_items_approver_nonblank",
        "ck_knowledge_items_not_self_replacing",
        "ck_knowledge_items_superseded_has_metadata",
    }
    replacement_index = next(
        index
        for index in table.indexes
        if index.name == "uq_knowledge_items_open_replacement"
    )
    assert replacement_index.unique is True
    assert [column.name for column in replacement_index.columns] == [
        "replaces_knowledge_item_id"
    ]


@pytest.mark.parametrize(
    "invalid_fields",
    [
        {"status": "approved"},
        {
            "status": "archived",
            "approved_at": datetime(2026, 8, 25, tzinfo=timezone.utc),
        },
        {
            "status": "draft",
            "approved_at": datetime(2026, 8, 25, tzinfo=timezone.utc),
            "approved_by": "owner",
        },
        {
            "status": "archived",
            "approved_at": datetime(2026, 8, 25, tzinfo=timezone.utc),
            "approved_by": "   ",
        },
        {"status": "superseded"},
    ],
)
def test_knowledge_approval_constraints_reject_inconsistent_rows(invalid_fields):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            KnowledgeItem(
                title="Knowledge",
                content="Content",
                **invalid_fields,
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()


def test_archived_approved_knowledge_retains_valid_approval_evidence():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    approved_at = datetime(2026, 8, 25, tzinfo=timezone.utc)
    with Session(engine) as session:
        item = KnowledgeItem(
            title="Knowledge",
            content="Content",
            status="archived",
            approved_at=approved_at,
            approved_by="owner",
        )
        session.add(item)
        session.flush()
        assert item.id is not None


def test_replacement_constraints_reject_self_reference_and_parallel_active_rows():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    approved_at = datetime(2026, 8, 25, tzinfo=timezone.utc)

    with Session(engine) as session:
        session.add(
            KnowledgeItem(
                id=77,
                title="Self",
                content="Content",
                replaces_knowledge_item_id=77,
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()

    with Session(engine) as session:
        source = KnowledgeItem(
            title="Source",
            content="Content",
            status="approved",
            approved_at=approved_at,
            approved_by="owner",
        )
        session.add(source)
        session.flush()
        session.add_all(
            [
                KnowledgeItem(
                    title="First",
                    content="Content",
                    replaces_knowledge_item_id=source.id,
                ),
                KnowledgeItem(
                    title="Second",
                    content="Content",
                    replaces_knowledge_item_id=source.id,
                ),
            ]
        )
        with pytest.raises(IntegrityError):
            session.flush()


def test_archived_replacement_allows_one_fresh_active_attempt():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    approved_at = datetime(2026, 8, 25, tzinfo=timezone.utc)
    with Session(engine) as session:
        source = KnowledgeItem(
            title="Source",
            content="Content",
            status="approved",
            approved_at=approved_at,
            approved_by="owner",
        )
        session.add(source)
        session.flush()
        session.add_all(
            [
                KnowledgeItem(
                    title="Archived attempt",
                    content="Content",
                    status="archived",
                    replaces_knowledge_item_id=source.id,
                ),
                KnowledgeItem(
                    title="Fresh attempt",
                    content="Content",
                    replaces_knowledge_item_id=source.id,
                ),
            ]
        )
        session.flush()
